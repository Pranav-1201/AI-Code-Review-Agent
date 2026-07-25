# ==========================================================
# File: repository_review_engine.py
# Purpose: Orchestrates repository-level AI code review
# ==========================================================

from typing import Dict, List

from backend.app.services.repo_analyzer import analyze_repository
from backend.app.services.llm_service import analyze_code
from backend.app.services.report_generator import generate_review_report
from backend.app.analysis.heuristic_refactor_engine import HeuristicRefactorEngine
from backend.app.analysis.dependency_analyzer import analyze_dependencies
from backend.app.analysis.dependency_graph import build_dependency_graph
from backend.app.analysis.duplicate_detector import detect_duplicates
from backend.app.services.security_analyzer import detect_security_issues
from backend.app.services.cache_manager import CacheManager
from backend.app.analysis.cohesion_analyzer import NO_SIZE_FLAG
from backend.app.analysis.taint_analyzer import propagate_interprocedural_taint
from backend.app.analysis.framework_detector import summarize_frameworks
from backend.app.analysis.architecture_analyzer import analyze_architecture

_cache_manager = CacheManager()


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
    cached_result = _cache_manager.get(code, imports, version="v3.4")
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
            "patch": None
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
        "suggestions": refactor_result.get("suggestions", []),
        "explanation": refactor_result.get("explanation", ""),
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

    _cache_manager.set(code, imports, final_output, version="v3.4")
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
                "snippet": f"Line {f.line}",
            })
            issues.append({
                "file": f.file, "type": "security", "severity": "critical",
                "message": desc,
                "why_it_matters": "Cross-function untrusted data reaching a dangerous "
                                  "sink enables remote exploitation.",
                "how_to_fix": "Sanitise or parameterise the value at the entry point.",
                "snippet": f"Line {f.line}", "confidence": f.confidence,
                "trust_boundary": "untrusted_input",
            })


# ==========================================================
# Repository Review Engine
# ==========================================================

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
        results = []

        total_score = 0
        issue_files = 0
        security_issues = 0

        # --------------------------------------------------
        # Run file analysis (only on code files)
        # --------------------------------------------------

        for file_data in repo_data:

            # Non-code files: add minimal report without AI analysis
            if not file_data.get("is_code", True):
                file_reports.append({
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
                    "improved_code": "",
                    "refactor_summary": "",
                    "content": file_data.get("content", ""),
                    "original_code": file_data.get("content", ""),
                    "documentation_coverage": 0,
                    "is_test": False,
                    "file_type": "non_code",
                    "file_role": "non_code",
                })
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

        all_issues = []

        # Separate production and test results for scoring
        prod_results = []
        test_results = []

        for result in results:

            # Normalize path
            fpath = result["file_path"].replace("\\", "/")
            result["file_path"] = fpath

            print(f"Processed file: {fpath}")

            file_report = {
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

                "improved_code": result.get("refactor_suggestion"),
                "refactor_summary": result.get("refactor_summary"),
                "patch": result.get("patch"),

                "content": result.get("content", ""),
                "original_code": result.get("content", ""),

                "documentation_coverage": result.get("documentation_coverage", 0),
                "time_complexity": result.get("complexity", "O(1)"),

                "is_test": result.get("is_test", False),
                "file_type": result.get("file_type", "production"),   # coarse
                "file_role": result.get("file_role", "utility"),      # fine (surfaced for UI)
            }

            file_reports.append(file_report)

            # Classify into production vs non-production for scoring
            if result.get("file_type") == "production":
                prod_results.append(result)
            else:
                test_results.append(result)

            # Count files with real issues (all code files)
            real_issues = [
                i for i in result.get("issues", [])
                if i.get("type") != "security"
                and "no obvious structural issues" not in str(i.get("message", "")).lower()
            ]

            if real_issues:
                issue_files += 1

            # Security issues: count only from production files
            if result.get("file_type") == "production":
                security_issues += len(result.get("security_risks", []))

            for issue in result.get("issues", []):
                msg = issue.get("message", "") if isinstance(issue, dict) else str(issue)
                if "no obvious structural issues" not in msg.lower():
                    all_issues.append(issue)

        # --------------------------------------------------
        # Compute averages from PRODUCTION files only
        # Test files and non-code files must not distort metrics
        # --------------------------------------------------

        prod_count = len(prod_results)
        total_file_count = len(file_reports)
        code_file_count = len(results)

        if prod_count > 0:
            # --------------------------------------------------
            # Source-stratified quality score
            # production=1.0, example=0.1, docs=0.05, test=0.0
            # Prevents example/docs files from fully diluting score
            # --------------------------------------------------
            FILE_TYPE_WEIGHTS = {
                "production": 1.0,
                "example":    0.1,
                "docs":       0.05,
                "test":       0.0,
            }
            weighted_sum = sum(
                r["score"] * FILE_TYPE_WEIGHTS.get(r.get("file_type", "production"), 1.0)
                for r in results
                if FILE_TYPE_WEIGHTS.get(r.get("file_type", "production"), 1.0) > 0
            )
            weight_total = sum(
                FILE_TYPE_WEIGHTS.get(r.get("file_type", "production"), 1.0)
                for r in results
                if FILE_TYPE_WEIGHTS.get(r.get("file_type", "production"), 1.0) > 0
            )
            avg_score = round(weighted_sum / weight_total, 2) if weight_total > 0 else 0
            avg_doc = round(
                sum(r.get("documentation_coverage", 0) for r in prod_results) / prod_count, 1
            )
            avg_cyclomatic = round(
                sum(r.get("cyclomatic_complexity", 0) for r in prod_results) / prod_count, 1
            )
        else:
            avg_score = 0
            avg_doc = 0
            avg_cyclomatic = 0

        # --------------------------------------------------
        # Compute health_score on the BACKEND
        # using production files only
        # --------------------------------------------------

        quality_score = avg_score
        sec_score = 100 if security_issues == 0 else max(0, round(100 - (security_issues ** 0.7) * 10))
        doc_score = avg_doc
        simplicity_score = max(0, round(100 - min(avg_cyclomatic * 3, 80)))

        health_score = round(
            0.35 * quality_score +
            0.25 * sec_score +
            0.20 * doc_score +
            0.20 * simplicity_score
        )

        # --------------------------------------------------
        # Group repeated issues by message pattern
        # --------------------------------------------------

        grouped_issues = []
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

        grouped_issues = list(issue_groups.values())
        
        # --------------------------------------------------
        # Dependency Graph Analysis (Centrality / Reuse)
        # --------------------------------------------------
        most_central_file = "None"
        most_reused_module = "None"
        
        if dependency_graph and "nodes" in dependency_graph and "links" in dependency_graph:
            in_degrees = {}
            out_degrees = {}
            for link in dependency_graph["links"]:
                src = link["source"]
                tgt = link["target"]
                out_degrees[src] = out_degrees.get(src, 0) + 1
                in_degrees[tgt] = in_degrees.get(tgt, 0) + 1
                
            if in_degrees:
                most_reused_module = max(in_degrees.items(), key=lambda x: x[1])[0]
            if out_degrees:
                most_central_file = max(out_degrees.items(), key=lambda x: x[1])[0]

        # --------------------------------------------------
        # Maintainability warnings
        # Detect long files and complex functions in prod code
        # --------------------------------------------------

        maintainability_warnings = []

        for r in prod_results:
            lines = r.get("lines", 0)
            fpath = r.get("file_path", "")
            cc = r.get("cyclomatic_complexity", 0)
            max_cc = r.get("max_cyclomatic_complexity", 0)

            # PHASE 2: cohesion-gated, reading the SAME should_flag_size
            # decision the file-level issue used. Previously this applied its
            # own flat `lines > 300`, so the repo warning and the file issue
            # could disagree.
            r_cohesion = r.get("cohesion") or NO_SIZE_FLAG
            if r_cohesion.get("should_flag_size"):
                maintainability_warnings.append({
                    "file": fpath,
                    "type": "long_file",
                    "message": r_cohesion.get("flag_reason")
                               or f"File is {lines} lines long with low cohesion — consider splitting",
                    "severity": "medium"
                })

            if max_cc > 10:
                maintainability_warnings.append({
                    "file": fpath,
                    "type": "complex_function",
                    "message": f"Contains function(s) with cyclomatic complexity {max_cc} — consider refactoring",
                    "severity": "medium" if max_cc <= 20 else "high"
                })

        # --------------------------------------------------
        # Insights Generation (Top Issues, Risks, Strengths)
        # --------------------------------------------------
        
        # Top 5 Critical Issues
        critical_issues = sorted(
            [i for i in grouped_issues if i.get("type") == "security" or i.get("severity") in ("critical", "high")],
            key=lambda x: (x.get("confidence", 0), x.get("count", 0)),
            reverse=True
        )[:5]
        
        # Most Complex Files
        complex_files = sorted(
            [f for f in prod_results if f.get("cyclomatic_complexity", 0) > 3],
            key=lambda x: x.get("cyclomatic_complexity", 0),
            reverse=True
        )[:5]

        insights = {
            "top_critical_issues": critical_issues,
            "most_complex_files": [{
                "file_path": f["file_path"],
                "cyclomatic_complexity": f.get("cyclomatic_complexity", 0),
                "score": f["score"]
            } for f in complex_files],
            "most_central_file": most_central_file,
            "most_reused_module": most_reused_module
        }

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
            "maintainability_warnings": maintainability_warnings,
        }

        visualizations = {
            "quality_scores": [r["score"] for r in results],
            "complexity": [r.get("cyclomatic_complexity", 0) for r in results],
            "lines": [r["lines"] for r in results]
        }

        # --------------------------------------------------
        # Map duplicates to file-level
        # --------------------------------------------------

        duplicate_map = {}
        for dup in duplicates:
            f1 = dup.get("file1", "")
            f2 = dup.get("file2", "")
            sim = dup.get("similarity", 100)

            if f1 not in duplicate_map:
                duplicate_map[f1] = []
            duplicate_map[f1].append({"file": f2, "similarity": sim})

            if f2 not in duplicate_map:
                duplicate_map[f2] = []
            duplicate_map[f2].append({"file": f1, "similarity": sim})

        for report in file_reports:
            fname = report.get("file_name", "")
            fpath = report.get("file_path", "")
            report["duplicates"] = duplicate_map.get(fpath, []) or duplicate_map.get(fname, [])

        # --------------------------------------------------
        # PHASE 4: framework fingerprint + architecture smells
        # (repo-level; real import-based evidence, replacing the
        #  filename-substring framework guess)
        # --------------------------------------------------
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

        summary["frameworks"] = frameworks
        summary["god_object_count"] = len(architecture.get("god_objects", []))
        summary["layer_violation_count"] = len(architecture.get("layer_violations", []))

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