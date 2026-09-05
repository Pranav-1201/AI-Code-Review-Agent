# ==========================================================
# File: repository_review_engine.py
# Purpose: Orchestrates repository-level AI code review
# ==========================================================

import ast
import sys
from typing import Dict, List, NamedTuple, Tuple

from backend.app.services.repo_analyzer import analyze_repository
from backend.app.services.llm_service import analyze_code
from backend.app.services.report_generator import generate_review_report
from backend.app.analysis.heuristic_refactor_engine import HeuristicRefactorEngine
from backend.app.analysis.dependency_analyzer import analyze_dependencies
from backend.app.analysis.dependency_graph import build_dependency_graph
from backend.app.analysis.duplicate_detector import detect_duplicates
from backend.app.services.security_analyzer import detect_security_issues
from backend.app.services.snippet import extract_snippet
from backend.app.services.cache_manager import CacheManager
from backend.app.analysis.cohesion_analyzer import NO_SIZE_FLAG
from backend.app.analysis.taint_analyzer import propagate_interprocedural_taint
from backend.app.analysis.framework_detector import summarize_frameworks
from backend.app.analysis.architecture_analyzer import analyze_architecture

_cache_manager = CacheManager()


# ----------------------------------------------------------
# S8: resolve dead-code names to locations
# ----------------------------------------------------------
# The detector returns bare names — `unused_imports` is a list of dotted
# import paths, `unused_functions` a list of simple names. Widening its
# contract to carry line numbers would break six assertions across the test
# suite and phase4_validation for no gain here, because this layer already
# holds the source. So the names are resolved back to lines here, once per
# file, and every dead-code finding ships with a real snippet rather than the
# `line: 0` placeholder J2 was built to eliminate.
# ----------------------------------------------------------

def _dead_code_locations(code: str):
    """Return ({importee: lineno}, {func_name: lineno}) for `code`.

    Import keys are rebuilt exactly as call_graph.build_import_graph builds
    `ImportEdge.importee`, so they match the names the detector reported.
    Returns two empty dicts for unparsable source; never raises.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return {}, {}

    imports: Dict[str, int] = {}
    functions: Dict[str, int] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.setdefault(alias.name, node.lineno)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                key = f"{module}.{alias.name}" if module else alias.name
                imports.setdefault(key, node.lineno)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.setdefault(node.name, node.lineno)
    return imports, functions


# ----------------------------------------------------------
# B4: "most reused module" must mean the user's own module
# ----------------------------------------------------------
# The insight was a raw max() over dependency-graph in-degree, so the
# standard library always won it. Measured on this repository the answer was
# `os` (50), then `sys` (38) and `typing` (31) — true, and useless. The
# genuinely reusable module here is the first-party one at 14.
#
# `sys.stdlib_module_names` is the authoritative list and needs no
# dependency. A third-party package is excluded by a different signal: it is
# a bare top-level name that no file in this repository provides.
# ----------------------------------------------------------

def first_party_prefixes(file_paths) -> "set":
    """Every module prefix the scanned repository itself provides.

    "backend/app/services/x.py" contributes backend, backend.app,
    backend.app.services and backend.app.services.x, plus the bare basename
    so that a flat `import helpers` next to helpers.py resolves too.
    """
    prefixes = set()
    for raw in file_paths or ():
        path = str(raw).replace("\\", "/")
        if path.endswith(".py"):
            path = path[:-3]
        segments = [seg for seg in path.split("/") if seg and seg != "."]
        if not segments:
            continue
        prefixes.add(segments[-1])
        for i in range(1, len(segments) + 1):
            prefixes.add(".".join(segments[:i]))
    return prefixes


def most_reused_first_party(dependency_graph: Dict, file_paths=None) -> str:
    """The most-imported module that belongs to the repository being scanned.

    `file_paths` is what makes "first party" decidable: a target is the
    user's own only if the repository actually provides that module. Without
    it, a third-party package is indistinguishable from a local one, because
    both appear in the graph purely as import targets.

    Returns "None" when the repository imports nothing of its own — an honest
    answer, and the same sentinel the field used before.
    """
    if not dependency_graph:
        return "None"
    links = dependency_graph.get("links") or []
    if not links:
        return "None"

    provided = first_party_prefixes(file_paths)
    # A link's SOURCE is definitionally a file in this repository, so it is a
    # sound fallback when no file list was supplied. A link's TARGET is not:
    # `requests` appears there exactly as a local module would.
    provided |= first_party_prefixes(
        str(link.get("source", "")) for link in links
    )

    in_degrees: Dict[str, int] = {}
    for link in links:
        target = str(link.get("target", ""))
        if not target:
            continue
        head = target.split(".")[0].split("/")[0]
        if head in sys.stdlib_module_names:
            continue
        stem = target[:-3] if target.endswith(".py") else target
        if stem in provided or head in provided:
            in_degrees[target] = in_degrees.get(target, 0) + 1

    if not in_degrees:
        return "None"
    # Sort by count desc then name asc, so a tie is stable across runs rather
    # than dependent on dict insertion order.
    return sorted(in_degrees.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]


# ----------------------------------------------------------
# Single File Analysis Worker
# ----------------------------------------------------------

def analyze_single_file(file_data: Dict, refactor_engine: HeuristicRefactorEngine,
                        explanation_depth: str = "senior") -> Dict:

    code = file_data["content"]
    file_name = file_data["file_name"]
    file_path = file_data.get("file_path", file_name)
    # Defect B: repo_analyzer now emits a real is_test; fall back to the fine role.
    file_is_test = file_data.get("is_test", file_data.get("file_role") == "test")
    # Defect C: the fine role must reach llm_service (was defaulting to 'utility').
    file_role = file_data.get("file_role", "utility")
    # PHASE 2: cohesion verdict computed once in repo_analyzer.
    file_cohesion = file_data.get("cohesion") or dict(NO_SIZE_FLAG)
    imports = file_data.get("imports", [])

    # Cache version history:
    #   v3.2  Chunk 0 - broken health-score / complexity results invalidated
    #   v3.3  Phase 2 - cohesion-gated size flagging changes issue output
    #   v3.4  Phase 3 - taint trust_boundary + reachability confidence on issues
    #   v3.5  Phase 5 - explanation_source label surfaced on the file report
    #   v3.6  Phase J3 - refactor_changes structured edits list added
    #   v3.7  Phase L  - dead_import/dead_function findings + file_type label
    #   v3.8  B2      - cyclomatic complexity counts comprehensions and
    #                   ternaries, and stops absorbing nested functions
    #
    # The cache key is (version, content, imports) — the file's ROLE was never
    # part of it, so two files with identical content and different roles
    # collided and whichever was analysed first won. That was already wrong
    # (the role drives is_test, which drives the security pass) and S9 makes
    # it unsound: a fixture whose content matches a production file would
    # serve the production result and leak its planted findings. Folding the
    # role into the version string fixes it without changing CacheManager.
    _cache_version = f"v3.8|{file_role}|{file_data.get('file_type', 'production')}"
    cached_result = _cache_manager.get(code, imports, version=_cache_version)
    if cached_result:
        return cached_result

    # SINGLE security analysis call per file — with full context:
    # - is_test_file: skips assert, downgrades subprocess
    # - file_path: framework-aware eval/exec/compile severity
    security_issues = detect_security_issues(
        code,
        is_test_file=file_is_test,
        file_path=file_path
    )

    functions = file_data.get("functions", [])
    imports = file_data.get("imports", [])
    complexity_metrics = file_data.get("complexity_metrics", [])
    smells = file_data.get("code_smells", [])

    # Inject metadata into complexity_metrics so llm_service
    # can access filename (for __main__.py guard suppression)
    # and doc_coverage (for explanation generation) without
    # changing the analyze_code() signature.
    if complexity_metrics:
        complexity_metrics[0]["_filename"] = file_path
        complexity_metrics[0]["_doc_coverage"] = file_data.get("documentation_coverage", 0.0)
    else:
        # Create a stub entry to carry metadata
        complexity_metrics = [{
            "max_loop_depth": 0,
            "cyclomatic_complexity": 1,
            "_filename": file_path,
            "_doc_coverage": file_data.get("documentation_coverage", 0.0),
            "_undocumented_count": file_data.get("undocumented_functions", 0)
        }]

    max_depth = 0
    for fn in complexity_metrics:
        max_depth = max(max_depth, fn.get("max_loop_depth", 0))

    complexity = {
        "max_loop_depth": max_depth
    }

    # ------------------------------------------------------
    # Safe AI analysis execution
    # ------------------------------------------------------

    try:

        analysis_result = analyze_code(
            code,
            functions=functions,
            imports=imports,
            complexity_metrics=complexity_metrics,
            language=file_data.get("language", "python"),
            security_issues=security_issues,
            is_test_file=file_is_test,
            file_role=file_role,     # Defect C: role-aware heuristics in llm_service
            cohesion=file_cohesion,  # PHASE 2: one size verdict for all outputs
            explanation_depth=explanation_depth,  # PHASE 5: junior/senior toggle
        )

        analysis_section = analysis_result.get("analysis", {})

        refactor_result = refactor_engine.generate_refactor(
            code,
            analysis_result,
            complexity,
            smells
        )

    except Exception as e:

        print(f"Analysis failed for {file_name}: {e}")

        analysis_result = {
            "code_quality_score": 0,
            "analysis": {
                "issues": [{
                    "type": "analysis_error",
                    "severity": "high",
                    "message": str(e)
                }],
                "security_risks": []
            }
        }

        analysis_section = analysis_result["analysis"]

        refactor_result = {
            "improved_code": "",
            "explanation": "",
            "suggestions": [],
            "patch": None,
            "changes": []
        }

    score = analysis_result.get("code_quality_score", 0)
    issues = analysis_section.get("issues", [])
    ai_security = analysis_section.get("security_risks", [])

    # --------------------------------------------------
    # Merge security issues (AI + static analyzer)
    # Deduplicate by description
    # --------------------------------------------------

    seen_descriptions = set()
    merged_security = []

    for sec in (ai_security + security_issues):
        if isinstance(sec, dict):
            desc = sec.get("description", "")
            if desc not in seen_descriptions:
                seen_descriptions.add(desc)
                merged_security.append(sec)
        elif isinstance(sec, str):
            # Legacy format: plain string
            if sec not in seen_descriptions:
                seen_descriptions.add(sec)
                merged_security.append({
                    "type": "Vulnerability",
                    "severity": "High",
                    "description": sec,
                    "recommendation": "",
                    "file": file_path,
                    "line": 0
                })

    # --------------------------------------------------
    # Format issues with proper categories
    # --------------------------------------------------

    formatted_issues = []

    for issue in issues:
        # Skip non-informational placeholder messages
        msg = issue.get("message", "") if isinstance(issue, dict) else str(issue)
        if "no obvious structural issues" in msg.lower():
            continue

        if isinstance(issue, dict):
            formatted_issues.append({
                "file": file_path,
                "type": issue.get("type", "code_issue"),
                "severity": issue.get("severity", "medium").lower(),
                "message": issue.get("message", ""),
                "why_it_matters": issue.get("why_it_matters", "Fixing this improves code quality and performance."),
                "how_to_fix": issue.get("how_to_fix", "Refactor the flagged area."),
                "snippet": issue.get("snippet", ""),
                "confidence": issue.get("confidence", 0.75)
            })
        else:
            formatted_issues.append({
                "file": file_path,
                "type": "code_issue",
                "severity": "medium",
                "message": str(issue),
                "why_it_matters": "Improves overall code quality.",
                "how_to_fix": "Review the code around this hint.",
                "snippet": "",
                "confidence": 0.5
            })

    # Add security issues as issues too (for issue explorer)
    for sec in merged_security:
        formatted_issues.append({
            "file": file_path,
            "type": "security",
            "severity": sec.get("severity", "High").lower(),
            "message": sec.get("description", str(sec)),
            "why_it_matters": sec.get("why_it_matters", "Security vulnerabilities can be exploited by attackers."),
            "how_to_fix": sec.get("how_to_fix", sec.get("recommendation", "Review secure coding practices.")),
            "snippet": sec.get("snippet", ""),
            "confidence": sec.get("confidence", 0.8),
            # PHASE 3: taint provenance (untrusted_input/operator_input/parameter/
            # internal/n-a) so the UI can explain WHY a sink is Critical vs Info.
            "trust_boundary": sec.get("trust_boundary", "n/a"),
        })

    # --------------------------------------------------
    # S8: dead code, which the detector has always found and the report has
    # always discarded. Scope is deliberate: dead imports everywhere, dead
    # functions in production files only — 374 of the 462 dead functions
    # measured against this repo are pytest tests, and reporting them would
    # turn this into the false-positive generator CONSTRAINTS.md 21 forbids.
    # --------------------------------------------------
    dead_code = file_data.get("dead_code") or {}
    dead_imports = dead_code.get("unused_imports") or []
    dead_functions = (dead_code.get("unused_functions") or []
                      if file_data.get("file_type") == "production" else [])

    if dead_imports or dead_functions:
        import_lines, function_lines = _dead_code_locations(code)
        source_lines = code.splitlines()

        for name in dead_imports:
            dead_line = import_lines.get(str(name), 0)
            formatted_issues.append({
                "file": file_path,
                "type": "dead_import",
                "severity": "low",
                "message": f"Unused import: {name}",
                "why_it_matters": (
                    "An import that is never used still costs load time, and "
                    "it misleads the next reader about what this module "
                    "actually depends on."
                ),
                "how_to_fix": f"Delete the `{name}` import.",
                "snippet": extract_snippet(source_lines, dead_line, context=1),
                # Alias-aware, with a single source of truth in call_graph,
                # so this is close to certain when it fires.
                "confidence": 0.9,
                "line": dead_line,
            })

        for name in dead_functions:
            dead_line = function_lines.get(str(name), 0)
            formatted_issues.append({
                "file": file_path,
                "type": "dead_function",
                "severity": "low",
                "message": f"Function `{name}` is never called",
                "why_it_matters": (
                    "Unreachable code is still read, still maintained and "
                    "still reviewed. It is the cheapest thing in a codebase "
                    "to delete."
                ),
                "how_to_fix": (
                    f"Confirm nothing outside this repository calls `{name}`, "
                    "then delete it."
                ),
                "snippet": extract_snippet(source_lines, dead_line, context=2),
                # Interprocedural, but deliberately conservative: dynamic
                # dispatch and reflection are not fully modelled.
                "confidence": 0.7,
                "line": dead_line,
            })

    # S9: a fixture corpus is planted, not found. Reporting our own bait as a
    # real finding is the defect. The file still appears in file_reports with
    # its real line count and language, so repository totals stay honest —
    # only its findings are suppressed.
    if file_role == "fixture":
        formatted_issues = []
        merged_security = []

    # S9: label every finding with the coarse type of the file it came from,
    # so findings in test files stay visible and filterable in the UI rather
    # than being silently dropped.
    coarse_type = file_data.get("file_type", "production")
    for _issue in formatted_issues:
        _issue["file_type"] = coarse_type

    lines = len(code.splitlines())
    language = file_data.get("language", "unknown")

    # Get metrics from repo analyzer
    file_cyclomatic = file_data.get("cyclomatic_complexity", 0)
    doc_coverage = file_data.get("documentation_coverage", 0)
    undocumented_count = file_data.get("undocumented_functions", 0)

    report = generate_review_report(
        file_name=file_name,
        analysis_result=analysis_result,
        refactor_result=refactor_result,
        complexity_metrics=complexity_metrics,
        smell_metrics=smells,
        undocumented_count=undocumented_count
    )

    final_output = {
        "file_path": file_path,
        "file_name": file_name,
        "language": language,
        "score": score,
        "cyclomatic_complexity": file_cyclomatic,
        "max_cyclomatic_complexity": file_data.get("max_cyclomatic_complexity", 0),
        "lines": lines,
        "issues": formatted_issues,
        "security_risks": merged_security,
        "report": report,
        "refactor_summary": refactor_result.get("explanation", ""),
        "refactor_suggestion": refactor_result.get("improved_code", ""),
        "patch": refactor_result.get("patch", None),
        # J3 (F4/F5): the structured edits behind `refactor_suggestion`, so the
        # UI can highlight exactly what changed and say so in prose instead of
        # re-deriving it from a rendered diff.
        "refactor_changes": refactor_result.get("changes", []),
        "suggestions": refactor_result.get("suggestions", []),
        "explanation": refactor_result.get("explanation", ""),
        # PHASE 5: label whether `explanation` was produced by the LLM layer or
        # the deterministic fallback, so the repo-scan path carries it too.
        "explanation_source": analysis_section.get("explanation_source", "deterministic"),
        "breakdown": analysis_result.get("breakdown", {}),
        "content": code,
        "documentation_coverage": doc_coverage,
        "undocumented_functions": undocumented_count,
        "is_test": file_is_test,
        "file_type": file_data.get("file_type", "production"),   # coarse
        "file_role": file_role,                                   # fine (surfaced for UI)
        # Carry the real per-file time complexity computed by repo_analyzer
        # (was dropped here, so file_report defaulted to "O(1)" for everything).
        "complexity": file_data.get("time_complexity", "O(1)"),
        # PHASE 2: carry the cohesion verdict so the repo-level
        # maintainability warning reads the same decision as the file issues.
        "cohesion": file_cohesion,
    }

    _cache_manager.set(code, imports, final_output, version=_cache_version)
    return final_output


# ==========================================================
# PHASE 4: Inter-procedural taint escalation (repo-level)
# ----------------------------------------------------------
# The per-file security pass is intra-procedural: a sink whose argument is
# a bare parameter is reported at the "parameter" trust boundary. Once every
# file is analysed we know the call graph, so we can escalate those sinks to
# untrusted/Critical when a caller actually passes untrusted input into the
# parameter. Upgrades the existing finding in place (no duplicate), keeping
# security_risks and the issue-explorer copy consistent.
# ==========================================================

def _category_to_type(category: str) -> str:
    return {
        "code_exec": "Dangerous Function",
        "command": "Command Injection",
        "deserialization": "Unsafe Deserialization",
    }.get(category, "Vulnerability")


def apply_interprocedural_taint(results: List[Dict]) -> None:
    """Escalate per-file sink findings that inter-procedural taint proves are
    reachable from untrusted input across function calls. Mutates `results`
    in place. Best-effort — never raises out."""
    try:
        sources = {r["file_path"]: r.get("content", "") for r in results
                   if r.get("content")}
        findings = propagate_interprocedural_taint(sources)
    except Exception:
        return

    by_path: Dict[str, Dict] = {}
    for r in results:
        by_path[r["file_path"]] = r
        by_path[r["file_path"].replace("\\", "/")] = r

    for f in findings:
        r = by_path.get(f.file) or by_path.get(f.file.replace("\\", "/"))
        if not r:
            continue
        finding_source = (sources.get(f.file) or sources.get(f.file.replace("\\", "/")) or "")
        # split("\n"), not splitlines(): see security_analyzer.py's
        # _source_lines for why splitlines() drifts the snippet out of
        # alignment with the AST-derived line number.
        finding_lines = finding_source.split("\n")
        note = (f" Argument is reachable from untrusted input ({f.source_kind}) "
                f"through a call chain — remote code/command execution risk.")
        risks = r.setdefault("security_risks", [])
        issues = r.setdefault("issues", [])

        matched = next((s for s in risks
                        if isinstance(s, dict) and s.get("line") == f.line), None)
        if matched:
            old_desc = matched.get("description", "")
            matched["severity"] = "Critical"
            matched["trust_boundary"] = "untrusted_input"
            matched["confidence"] = max(matched.get("confidence", 0) or 0, f.confidence)
            if "call chain" not in old_desc:
                matched["description"] = old_desc + note
            # keep the issue-explorer copy (matched by original description) in sync
            for iss in issues:
                if isinstance(iss, dict) and iss.get("type") == "security" \
                        and iss.get("message") == old_desc:
                    iss["severity"] = "critical"
                    iss["trust_boundary"] = "untrusted_input"
                    iss["confidence"] = matched["confidence"]
                    iss["message"] = matched["description"]
        else:
            desc = (f"{f.sink_name}() receives an argument reachable from untrusted "
                    f"input ({f.source_kind}) through a call chain — remote "
                    f"code/command execution risk.")
            risks.append({
                "type": _category_to_type(f.category), "severity": "Critical",
                "description": desc,
                "recommendation": "Validate or parameterise the value at the trust "
                                  "boundary before it reaches the sink.",
                "line": f.line, "confidence": f.confidence,
                "trust_boundary": "untrusted_input",
                "why_it_matters": "Cross-function untrusted data reaching a dangerous "
                                  "sink enables remote exploitation.",
                "how_to_fix": "Sanitise or parameterise the value at the entry point.",
                "snippet": extract_snippet(finding_lines, f.line),
            })
            issues.append({
                "file": f.file, "type": "security", "severity": "critical",
                "message": desc,
                "why_it_matters": "Cross-function untrusted data reaching a dangerous "
                                  "sink enables remote exploitation.",
                "how_to_fix": "Sanitise or parameterise the value at the entry point.",
                "snippet": extract_snippet(finding_lines, f.line), "confidence": f.confidence,
                "trust_boundary": "untrusted_input",
            })


# ==========================================================
# Repository Review Engine
# ==========================================================

# ----------------------------------------------------------
# B1: the per-file report pipeline
# ----------------------------------------------------------
# Two builders produce every row of the file table — one for files the
# analyzer skipped, one for files it analysed. They must agree on their keys
# or the frontend reads undefined off half the table; test_b1_contract.py
# pins the difference between them.
# ----------------------------------------------------------

def _non_code_file_report(file_data: Dict) -> Dict:
    """The minimal report for a file the analyzer does not read.

    Scored 100 rather than 0: a README is not a low-quality source file, it is
    not a source file. It is excluded from every average by `file_type`.
    """
    return {
        "file_path": file_data["file_path"],
        "file_name": file_data["file_name"],
        "score": 100,
        "language": file_data.get("language", "unknown"),
        "lines": file_data.get("lines", 0),
        "lines_of_code": file_data.get("lines", 0),
        "complexity": "N/A",
        "cyclomatic_complexity": 0,
        "max_cyclomatic_complexity": 0,
        "issues": [],
        "security_risks": [],
        "suggestions": [],
        "explanation": "",
        "explanation_source": "deterministic",
        "improved_code": "",
        "refactor_summary": "",
        "content": file_data.get("content", ""),
        "original_code": file_data.get("content", ""),
        "documentation_coverage": 0,
        "is_test": False,
        "file_type": "non_code",
        "file_role": "non_code",
    }


def _file_report_from_result(result: Dict, fpath: str) -> Dict:
    """The report row for an analysed code file.

    `fpath` is passed in already normalised rather than re-derived, so the
    path written here and the path written back onto `result` cannot drift.
    """
    return {
        "file_path": fpath,
        "file_name": result.get("file_name", ""),

        "score": result.get("score", 0),
        "language": result.get("language", "unknown"),

        "lines": result.get("lines", 0),
        "lines_of_code": result.get("lines", 0),

        "complexity": result.get("complexity", "O(1)"),
        "cyclomatic_complexity": result.get("cyclomatic_complexity", 0),
        "max_cyclomatic_complexity": result.get("max_cyclomatic_complexity", 0),

        "issues": result.get("issues", []),

        "security_risks": result.get("security_risks", []),

        "suggestions": result.get("suggestions", []),
        "explanation": result.get("explanation", ""),
        # PHASE 5: "llm" | "deterministic" — carried onto the file report.
        "explanation_source": result.get("explanation_source", "deterministic"),

        "improved_code": result.get("refactor_suggestion"),
        "refactor_summary": result.get("refactor_summary"),
        "patch": result.get("patch"),
        # J3 (F4/F5): the structured edits behind refactor_suggestion
        "refactor_changes": result.get("refactor_changes", []),

        "content": result.get("content", ""),
        "original_code": result.get("content", ""),

        "documentation_coverage": result.get("documentation_coverage", 0),
        "time_complexity": result.get("complexity", "O(1)"),

        "is_test": result.get("is_test", False),
        "file_type": result.get("file_type", "production"),   # coarse
        "file_role": result.get("file_role", "utility"),      # fine (surfaced for UI)
    }


def _is_real_issue(issue) -> bool:
    """A structural issue, as opposed to the analyzer's "nothing found" note.

    The placeholder is matched on its text because it arrives as an ordinary
    issue; both counters below have to exclude it or every clean file counts
    as a file with issues.

    The two inlined filters this replaces disagreed on one detail: the
    issue-file count coerced the message with `str()`, the all_issues loop did
    not. Coercing is the safer of the two and changes nothing for the string
    messages every producer actually emits.
    """
    msg = issue.get("message", "") if isinstance(issue, dict) else issue
    return "no obvious structural issues" not in str(msg).lower()


class _Aggregates(NamedTuple):
    """One pass over the analysed files, in the shape the report needs."""
    all_issues: List[Dict]
    prod_results: List[Dict]
    test_results: List[Dict]
    issue_files: int
    security_issues: int


def _aggregate_results(results: List[Dict], file_reports: List[Dict]) -> _Aggregates:
    """Build the code-file report rows and the counters over them.

    Appends into the caller's `file_reports`, which already holds the non-code
    rows, so the table keeps the order it has always had: non-code first, then
    code in analysis order.
    """
    all_issues: List[Dict] = []
    prod_results: List[Dict] = []
    test_results: List[Dict] = []
    issue_files = 0
    security_issues = 0

    for result in results:

        # Normalize path
        fpath = result["file_path"].replace("\\", "/")
        result["file_path"] = fpath

        print(f"Processed file: {fpath}")

        file_reports.append(_file_report_from_result(result, fpath))

        # Classify into production vs non-production for scoring
        is_production = result.get("file_type") == "production"
        if is_production:
            prod_results.append(result)
        else:
            test_results.append(result)

        issues = result.get("issues", [])

        # Count files with real issues (all code files). A security finding is
        # reported separately and does not make this a "file with issues".
        if [i for i in issues
                if i.get("type") != "security" and _is_real_issue(i)]:
            issue_files += 1

        # Security issues: count only from production files
        if is_production:
            security_issues += len(result.get("security_risks", []))

        all_issues.extend(i for i in issues if _is_real_issue(i))

    return _Aggregates(all_issues, prod_results, test_results,
                       issue_files, security_issues)


# ----------------------------------------------------------
# B1: scoring
# ----------------------------------------------------------

#: Source-stratified quality weighting. Prevents example and docs files from
#: fully diluting the score, and keeps test files out of it entirely. A weight
#: of 0 excludes a file from both the numerator and the denominator, so tests
#: neither help nor hurt.
FILE_TYPE_WEIGHTS = {
    "production": 1.0,
    "example":    0.1,
    "docs":       0.05,
    "test":       0.0,
}


def _file_type_weight(result: Dict) -> float:
    return FILE_TYPE_WEIGHTS.get(result.get("file_type", "production"), 1.0)


class _Averages(NamedTuple):
    """Averages over PRODUCTION files, except `score` which is weighted.

    Test and non-code files must not distort the metrics; documentation and
    complexity are therefore straight means over production files only, while
    the quality score uses FILE_TYPE_WEIGHTS so an examples directory counts
    for a little rather than nothing or everything.
    """
    score: float
    documentation: float
    cyclomatic: float


def _compute_averages(results: List[Dict], prod_results: List[Dict]) -> _Averages:
    prod_count = len(prod_results)
    if prod_count == 0:
        return _Averages(0, 0, 0)

    weighted = [(r, _file_type_weight(r)) for r in results]
    weighted_sum = sum(r["score"] * w for r, w in weighted if w > 0)
    weight_total = sum(w for _, w in weighted if w > 0)

    return _Averages(
        score=round(weighted_sum / weight_total, 2) if weight_total > 0 else 0,
        documentation=round(
            sum(r.get("documentation_coverage", 0) for r in prod_results) / prod_count, 1),
        cyclomatic=round(
            sum(r.get("cyclomatic_complexity", 0) for r in prod_results) / prod_count, 1),
    )


class _HealthScore(NamedTuple):
    """The four dimensions of the composite, and the composite itself.

    The weights are surfaced in the UI (F14), so they are named here rather
    than left as bare literals in an arithmetic expression.
    """
    quality: float
    security: int
    documentation: float
    simplicity: int
    composite: int


def _compute_health_score(averages: _Averages, security_issues: int) -> _HealthScore:
    """Compute health on the BACKEND, from production files only.

    Note what happens with nothing to measure: quality and documentation are
    0, but security and simplicity have nothing to subtract from and come out
    at 100, so an unanalysable repository scores 45. That is why B6 rejects
    such a repository upstream rather than showing this number to anyone.
    """
    security = (100 if security_issues == 0
                else max(0, round(100 - (security_issues ** 0.7) * 10)))
    simplicity = max(0, round(100 - min(averages.cyclomatic * 3, 80)))

    composite = round(
        0.35 * averages.score +
        0.25 * security +
        0.20 * averages.documentation +
        0.20 * simplicity
    )
    return _HealthScore(averages.score, security, averages.documentation,
                        simplicity, composite)


# ----------------------------------------------------------
# B1: the repo-level report sections
# ----------------------------------------------------------

def _group_issues(all_issues: List[Dict]) -> List[Dict]:
    """Collapse repeated issues by message, counting the files they hit.

    The first occurrence supplies every other field, so a grouped issue keeps
    the line and snippet of whichever file reported it first.
    """
    issue_groups: Dict[str, Dict] = {}

    for issue in all_issues:
        msg = issue.get("message", "") if isinstance(issue, dict) else str(issue)
        # Normalize message for grouping (remove numbers, file-specific parts)
        key = msg.lower().strip()

        if key in issue_groups:
            issue_groups[key]["count"] += 1
            file = issue.get("file", "")
            if file and file not in issue_groups[key]["affected_files"]:
                issue_groups[key]["affected_files"].append(file)
        else:
            issue_groups[key] = {
                **issue,
                "count": 1,
                "affected_files": [issue.get("file", "")]
            }

    return list(issue_groups.values())


def _graph_centrality(dependency_graph: Dict, repo_data) -> Tuple[str, str]:
    """(most central file, most reused first-party module).

    Central means most outgoing imports — the file that depends on the most
    other things, which is where a change is most likely to break something.
    Both default to the string "None", which is what the UI renders.
    """
    if not (dependency_graph
            and "nodes" in dependency_graph
            and "links" in dependency_graph):
        return "None", "None"

    out_degrees: Dict[str, int] = {}
    for link in dependency_graph["links"]:
        src = link["source"]
        out_degrees[src] = out_degrees.get(src, 0) + 1

    # B4: the raw max() here always returned a stdlib module.
    most_reused_module = most_reused_first_party(
        dependency_graph,
        [f.get("file_path", "") for f in repo_data],
    )
    most_central_file = (max(out_degrees.items(), key=lambda x: x[1])[0]
                         if out_degrees else "None")
    return most_central_file, most_reused_module


def _maintainability_warnings(prod_results: List[Dict]) -> List[Dict]:
    """Long files and complex functions, production code only."""
    warnings: List[Dict] = []

    for r in prod_results:
        lines = r.get("lines", 0)
        fpath = r.get("file_path", "")
        max_cc = r.get("max_cyclomatic_complexity", 0)

        # PHASE 2: cohesion-gated, reading the SAME should_flag_size decision
        # the file-level issue used. Previously this applied its own flat
        # `lines > 300`, so the repo warning and the file issue could disagree.
        r_cohesion = r.get("cohesion") or NO_SIZE_FLAG
        if r_cohesion.get("should_flag_size"):
            warnings.append({
                "file": fpath,
                "type": "long_file",
                "message": r_cohesion.get("flag_reason")
                           or f"File is {lines} lines long with low cohesion — consider splitting",
                "severity": "medium"
            })

        if max_cc > 10:
            warnings.append({
                "file": fpath,
                "type": "complex_function",
                "message": f"Contains function(s) with cyclomatic complexity {max_cc} — consider refactoring",
                "severity": "medium" if max_cc <= 20 else "high"
            })

    return warnings


def _build_insights(grouped_issues: List[Dict], prod_results: List[Dict],
                    most_central_file: str, most_reused_module: str) -> Dict:
    """The five-item summaries the dashboard leads with."""

    # Top 5 Critical Issues
    critical_issues = sorted(
        [i for i in grouped_issues
         if i.get("type") == "security" or i.get("severity") in ("critical", "high")],
        key=lambda x: (x.get("confidence", 0), x.get("count", 0)),
        reverse=True
    )[:5]

    # Most Complex Files
    complex_files = sorted(
        [f for f in prod_results if f.get("cyclomatic_complexity", 0) > 3],
        key=lambda x: x.get("cyclomatic_complexity", 0),
        reverse=True
    )[:5]

    return {
        "top_critical_issues": critical_issues,
        "most_complex_files": [{
            "file_path": f["file_path"],
            "cyclomatic_complexity": f.get("cyclomatic_complexity", 0),
            "score": f["score"]
        } for f in complex_files],
        "most_central_file": most_central_file,
        "most_reused_module": most_reused_module
    }


def _attach_duplicates(file_reports: List[Dict], duplicates: List[Dict]) -> None:
    """Write each file's duplicate partners onto its report row.

    Matched on path first and file name second: the detector reports whichever
    it has, and a bare name still has to find its row.
    """
    duplicate_map: Dict[str, List[Dict]] = {}
    for dup in duplicates:
        f1 = dup.get("file1", "")
        f2 = dup.get("file2", "")
        sim = dup.get("similarity", 100)

        duplicate_map.setdefault(f1, []).append({"file": f2, "similarity": sim})
        duplicate_map.setdefault(f2, []).append({"file": f1, "similarity": sim})

    for report in file_reports:
        fname = report.get("file_name", "")
        fpath = report.get("file_path", "")
        report["duplicates"] = (duplicate_map.get(fpath, [])
                                or duplicate_map.get(fname, []))


def _architecture_summary(results: List[Dict]) -> Tuple[Dict, Dict]:
    """PHASE 4: framework fingerprint + architecture smells.

    Repo-level, from real import-based evidence, replacing the filename
    substring framework guess.

    Both analyses are fail-soft on purpose: a repository that breaks one of
    them still gets a report, minus that section. They are informational, and
    no score depends on them.
    """
    code_sources = {r["file_path"]: r.get("content", "")
                    for r in results if r.get("content")}
    try:
        frameworks = summarize_frameworks(code_sources)
    except Exception:
        frameworks = {}
    try:
        architecture = analyze_architecture(code_sources)
    except Exception:
        architecture = {"god_objects": [], "layer_violations": []}

    return frameworks, architecture


class RepositoryReviewEngine:

    def __init__(self):
        self.refactor_engine = HeuristicRefactorEngine()

    def review_repository(self, repo_path: str, repo_data,
                          explanation_depth: str = "senior") -> Dict:

        # --------------------------------------------------
        # Repo-level analysis
        # --------------------------------------------------

        dependencies = analyze_dependencies(repo_path)
        dependency_graph = build_dependency_graph(repo_data)
        duplicates = detect_duplicates(repo_data)

        file_reports: List[Dict] = []
        results: List[Dict] = []

        # --------------------------------------------------
        # Run file analysis (only on code files)
        # --------------------------------------------------

        for file_data in repo_data:

            # Non-code files: add minimal report without AI analysis
            if not file_data.get("is_code", True):
                file_reports.append(_non_code_file_report(file_data))
                continue

            result = analyze_single_file(file_data, self.refactor_engine,
                                         explanation_depth=explanation_depth)
            results.append(result)

        # Phase 4: escalate sinks reachable from untrusted input across
        # function calls now that every file (hence the call graph) is known.
        apply_interprocedural_taint(results)

        # --------------------------------------------------
        # Aggregate results
        # --------------------------------------------------

        agg = _aggregate_results(results, file_reports)
        all_issues = agg.all_issues
        prod_results = agg.prod_results
        test_results = agg.test_results
        issue_files = agg.issue_files
        security_issues = agg.security_issues

        # --------------------------------------------------
        # Scoring — production files only, computed on the backend
        # --------------------------------------------------

        prod_count = len(prod_results)
        total_file_count = len(file_reports)
        code_file_count = len(results)

        averages = _compute_averages(results, prod_results)
        avg_score = averages.score
        avg_doc = averages.documentation
        avg_cyclomatic = averages.cyclomatic

        health_score = _compute_health_score(averages, security_issues).composite

        # --------------------------------------------------
        # Repo-level sections
        # --------------------------------------------------

        grouped_issues = _group_issues(all_issues)
        most_central_file, most_reused_module = _graph_centrality(
            dependency_graph, repo_data)
        insights = _build_insights(grouped_issues, prod_results,
                                   most_central_file, most_reused_module)
        _attach_duplicates(file_reports, duplicates)
        frameworks, architecture = _architecture_summary(results)

        summary = {
            "files_analyzed": total_file_count,
            "code_files": code_file_count,
            "production_files": prod_count,
            "non_production_files": len(test_results),
            "files_with_issues": issue_files,
            "average_quality_score": avg_score,
            "total_security_issues": security_issues,
            "lines_of_code": sum(r["lines"] for r in results),
            "avg_documentation_coverage": avg_doc,
            "avg_cyclomatic_complexity": avg_cyclomatic,
            "health_score": health_score,
            "maintainability_warnings": _maintainability_warnings(prod_results),
            "frameworks": frameworks,
            "god_object_count": len(architecture.get("god_objects", [])),
            "layer_violation_count": len(architecture.get("layer_violations", [])),
        }

        visualizations = {
            "quality_scores": [r["score"] for r in results],
            "complexity": [r.get("cyclomatic_complexity", 0) for r in results],
            "lines": [r["lines"] for r in results]
        }

        # --------------------------------------------------
        # Final repository report
        # --------------------------------------------------

        return {
            "repository_summary": summary,
            "file_reports": file_reports,
            "issues": grouped_issues,
            "dependencies": dependencies,
            "dependency_graph": dependency_graph,
            "duplicates": duplicates,
            "visualizations": visualizations,
            "insights": insights,
            "frameworks": frameworks,
            "architecture": architecture,
        }