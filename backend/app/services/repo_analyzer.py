# ==========================================================
# File: repo_analyzer.py
# Purpose: Repository scanning and structural analysis
# ==========================================================

import os
import ast
from pathlib import Path
from typing import List, Dict
from concurrent.futures import ProcessPoolExecutor

from backend.app.analysis.ast_parser import parse_python_file
from backend.app.analysis.dead_code_detector import DeadCodeDetector
from backend.app.analysis.complexity_analyzer import ComplexityAnalyzer
from backend.app.analysis.cohesion_analyzer import size_verdict, NO_SIZE_FLAG
from backend.app.analysis import js_structure
from backend.app.services import incremental


# ----------------------------------------------------------
# Supported extensions — restricted to Java, C++, JS/TS, Python
# ----------------------------------------------------------

CODE_EXTENSIONS = (
    ".py", ".js", ".jsx", ".ts", ".tsx",
    ".java", ".cpp", ".c", ".h", ".hpp", ".cc", ".cxx"
)

# JS/TS family — these get tree-sitter structural analysis (Phase 6 / Chunk 5)
# via js_structure, mirroring the Python AST path. Everything else in
# CODE_EXTENSIONS (Java, C/C++) still gets metadata only.
JS_TS_EXTENSIONS = (".js", ".jsx", ".ts", ".tsx")

# Completely ignore non-code files
NON_CODE_EXTENSIONS = ()

ALL_EXTENSIONS = CODE_EXTENSIONS

IGNORED_DIRECTORIES = {
    ".git", "__pycache__", "node_modules",
    ".venv", "venv", "env",
    "dist", "build", ".tox", ".mypy_cache",
    ".pytest_cache", ".eggs", "egg-info",
    ".idea", ".vscode",
}

# ----------------------------------------------------------
# Language Detection
# ----------------------------------------------------------

LANGUAGE_MAP = {
    ".py": "Python",
    ".js": "JavaScript", ".jsx": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript",
    ".html": "HTML", ".htm": "HTML",
    ".css": "CSS", ".scss": "SCSS", ".less": "Less", ".sass": "Sass",
    ".java": "Java",
    ".cpp": "C++", ".c": "C", ".h": "C", ".hpp": "C++",
    ".go": "Go",
    ".rs": "Rust",
    ".rb": "Ruby",
    ".php": "PHP",
    ".swift": "Swift",
    ".kt": "Kotlin",
    ".scala": "Scala",
    ".cs": "C#",
    ".json": "JSON",
    ".yaml": "YAML", ".yml": "YAML",
    ".toml": "TOML",
    ".xml": "XML", ".svg": "XML",
    ".md": "Markdown", ".rst": "reStructuredText",
    ".sql": "SQL",
    ".sh": "Shell", ".bat": "Batch", ".ps1": "PowerShell",
    ".cfg": "Config", ".ini": "Config", ".env": "Config",
    ".txt": "Text",
    ".dockerfile": "Dockerfile",
}


def detect_language(filename: str) -> str:
    ext = os.path.splitext(filename.lower())[1]
    return LANGUAGE_MAP.get(ext, "Unknown")


def count_lines(code: str) -> int:
    return len(code.splitlines())


# ----------------------------------------------------------
# Test File Detection
# ----------------------------------------------------------

# ----------------------------------------------------------
# S9: fixture corpora are not production code
# ----------------------------------------------------------
# A planted-vulnerability corpus exists to be scanned, not to be
# reported on. Ours lives under benchmark/corpus/fixtures/, but the
# rule is written generically: a scanned third-party repo's own
# fixture corpus is not its production code either.
# ----------------------------------------------------------
_FIXTURE_PATH_MARKERS = (
    "/benchmark/corpus/",
    "/fixtures/",
    "/corpus/",
    "/testdata/",
)


def classify_file_type(file_path: str, content: str = "") -> str: # PHASE 1: added content
    """
    Classify file as production, test, example, or docs based on path.
    Only production files contribute to the repository health score.
    """
    # PHASE 1: 2-pass role classifier
    path_lower = file_path.replace("\\", "/").lower()
    filename = os.path.basename(path_lower)

    # The leading "/" lets a repo-relative path such as "fixtures/a.py" match
    # the same rule as "pkg/fixtures/a.py".
    if any(marker in f"/{path_lower}" for marker in _FIXTURE_PATH_MARKERS):
        return 'fixture'
    if any(seg in path_lower for seg in ('/test/', '/tests/', '/spec/')):
        return 'test'
    if filename.startswith('test_') or filename.endswith('_test.py') or filename == 'conftest.py':
        return 'test'
    if any(seg in filename for seg in ('cli', 'command', 'cmd')):
        return 'cli_parser'
    if any(seg in filename for seg in ('model', 'schema', 'entity', 'dto')):
        return 'data_model'
        
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return 'utility'
        
    has_cli_import = any(
        (isinstance(node, ast.Import) and any(a.name in ('click', 'argparse') for a in node.names))
        or (isinstance(node, ast.ImportFrom) and getattr(node, 'module', None) in ('click', 'argparse'))
        for node in ast.walk(tree)
    )
    func_count = sum(1 for n in ast.walk(tree) if isinstance(n, ast.FunctionDef))
    if has_cli_import and func_count > 10:
        return 'cli_parser'
        
    ORCHESTRATOR_BASES = {
        'Flask', 'Blueprint', 'FastAPI', 'APIRouter',
        'BaseView', 'View', 'MethodView', 'Router',
        'WSGIApplication', 'Application',
    }
    
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for base in node.bases:
                base_name = (
                    base.id if isinstance(base, ast.Name)
                    else getattr(base, 'attr', '')
                )
                if base_name in ORCHESTRATOR_BASES:
                    return 'orchestrator'

    return 'utility'


# ----------------------------------------------------------
# Two-field contract (Chunk 0 — fixes Defect A)
# ----------------------------------------------------------
# classify_file_type() returns a FINE role, used only for
# role-aware complexity thresholds: one of
#   {test, cli_parser, data_model, utility, orchestrator}.
# The score aggregation (repository_review_engine) and the
# frontend understand only a COARSE type:
#   {production, test, non_code}.
# coarse_file_type() maps fine -> coarse so both layers agree.
# Previously the fine role was stored in `file_type`, and the
# aggregator filtered `file_type == 'production'` — which a fine
# role never equals — so every production file was dropped and
# the health score collapsed to a constant.
# ----------------------------------------------------------

_NON_PRODUCTION_ROLES = frozenset({"test", "non_code", "fixture"})

# S9: `fixture` is a sixth FINE role but must not become a fourth COARSE
# value — the scoring layer and the frontend understand exactly three.
# Fixtures are scored and displayed as test files; only their findings are
# suppressed, at the report layer.
_COARSE_OVERRIDES = {"fixture": "test"}


def coarse_file_type(file_role: str) -> str:
    """Map a fine role to the coarse scoring/frontend type."""
    if file_role in _NON_PRODUCTION_ROLES:
        return _COARSE_OVERRIDES.get(file_role, file_role)
    return "production"


# ----------------------------------------------------------
# Documentation Coverage (Python)
# ----------------------------------------------------------

# PHASE 1: Docstring suppression predicates
_LIFECYCLE_METHODS = frozenset({
    'setUp', 'tearDown', 'setUpClass', 'tearDownClass',
    'setUpModule', 'tearDownModule',
})

def _should_suppress_docstring_warning(func_name: str) -> bool:
    """Return True for functions that must not be flagged for missing docstrings."""
    if func_name.startswith('_'):        # private / dunder
        return True
    if func_name.startswith('test_'):    # pytest-style tests
        return True
    if func_name[0].isupper() and func_name.startswith('Test'):  # TestFooBar class
        return True
    if func_name in _LIFECYCLE_METHODS:
        return True
    return False

def compute_doc_coverage(code: str, language: str) -> tuple[float, int]:
    if language != "Python":
        return 0.0, 0

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return 0.0, 0

    total = 0
    documented = 0

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            # PHASE 1: exempt private, test, and lifecycle functions
            if _should_suppress_docstring_warning(node.name):
                continue
            total += 1
            if (node.body
                and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)):
                documented += 1

    if total == 0:
        return 0.0, 0

    return round((documented / total) * 100, 1), (total - documented)


# ----------------------------------------------------------
# Worker Function
# ----------------------------------------------------------

def _analyze_file_worker(args):

    path, repo_path = args

    dead_code_detector = DeadCodeDetector()
    complexity_analyzer = ComplexityAnalyzer()

    file_name = path.name
    language = detect_language(file_name)
    ext = path.suffix.lower()

    # Skip very large files
    if path.stat().st_size > 200_000:
        return None

    try:
        code = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None

    # Skip empty files
    lines_clean = [l for l in code.splitlines() if l.strip()]
    if len(lines_clean) < 1:
        return None

    lines = count_lines(code)

    # Normalize path to forward slashes always
    try:
        relative_path = str(path.relative_to(repo_path)).replace("\\", "/")
    except ValueError:
        relative_path = str(path).replace("\\", "/")

    # --------------------------------------------------
    # Non-code files: just track metadata
    # --------------------------------------------------
    if ext not in CODE_EXTENSIONS:
        return {
            "file_name": file_name,
            "file_path": relative_path,
            "language": language,
            "lines": lines,
            "functions": [],
            "imports": [],
            "dead_code": {"unused_imports": [], "unused_variables": []},
            "code_smells": {},
            "complexity_metrics": [],
            "cyclomatic_complexity": None,
            "max_cyclomatic_complexity": None,
            "time_complexity": None,
            "documentation_coverage": None,
            "content": code,
            "is_code": False,
            "file_type": "non_code",   # coarse (scoring/frontend)
            "file_role": "non_code",   # fine (thresholds)
            "is_test": False,
            "cohesion": dict(NO_SIZE_FLAG),
        }

    # --------------------------------------------------
    # Code files: full analysis
    # --------------------------------------------------
    analysis = {"functions": [], "imports": []}

    # Chunk 0 two-field contract:
    #   file_role = fine 5-tier role  -> drives complexity thresholds
    #   file_type = coarse type       -> drives scoring + frontend
    file_role = classify_file_type(relative_path, code)
    file_type = coarse_file_type(file_role)

    # PHASE 2: cohesion-gated size verdict, computed ONCE here.
    # Every downstream "this file is too long" claim reads
    # cohesion["should_flag_size"] instead of applying its own
    # line-count threshold.
    cohesion = size_verdict(code, relative_path) if ext == ".py" else dict(NO_SIZE_FLAG)

    # js holds the tree-sitter result for JS/TS so both the function inventory
    # and the complexity block below read it without parsing twice.
    js = {"functions": [], "complexity_metrics": []}

    if ext == ".py":
        try:
            analysis = parse_python_file(code)
        except Exception:
            pass
    elif ext in JS_TS_EXTENSIONS:
        # Phase 6 (Chunk 5): tree-sitter structural pass for JS/TS. Degrades to
        # empty (today's behaviour) if tree-sitter is unavailable — never raises.
        js = js_structure.analyze(code, ext, role=file_role)
        analysis = {"functions": js.get("functions", []), "imports": []}

    # Dead code detection (Python only)
    dead_code = {"unused_imports": [], "unused_variables": []}
    if ext == ".py":
        dead_code = dead_code_detector.analyze(code)

    # Complexity analysis (Python only)
    complexity_results = []

    if ext == ".py":
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    metrics = complexity_analyzer.analyze_function(node, role=file_role) # Chunk 0: thread FINE role
                    metrics["function"] = node.name
                    complexity_results.append(metrics)
        except Exception:
            pass
    elif ext in JS_TS_EXTENSIONS:
        # Same per-function shape as the Python branch, so the aggregation below
        # (file cyclomatic avg, max, time complexity) is language-agnostic.
        complexity_results = js.get("complexity_metrics", [])

    # --------------------------------------------------
    # Aggregate cyclomatic complexity
    # CC = AVERAGE of function CCs (not sum)
    # Also track max CC for hotspot detection
    # --------------------------------------------------
    file_cyclomatic = 0
    file_max_cyclomatic = 0
    file_time_complexity = "O(1)"

    if complexity_results:
        cc_values = [
            fn.get("cyclomatic_complexity", 0)
            for fn in complexity_results
        ]
        file_cyclomatic = round(sum(cc_values) / len(cc_values), 1)
        file_max_cyclomatic = max(cc_values)

        max_depth = max(
            fn.get("max_loop_depth", 0)
            for fn in complexity_results
        )

        depth_map = {0: "O(1)", 1: "O(n)", 2: "O(n²)", 3: "O(n³)"}
        file_time_complexity = depth_map.get(max_depth, "O(n^k)")

        has_recursive = any(fn.get("recursive", False) for fn in complexity_results)
        if has_recursive and max_depth <= 1:
            file_time_complexity = "O(n)"
    else:
        # No function definitions found — module-level file (e.g. __init__.py, signals.py)
        # Use baseline McCabe score of 1.0 to prevent 'undefined' showing in reports
        file_cyclomatic = 1.0
        file_max_cyclomatic = 1
        file_time_complexity = "O(1)"

    # Documentation coverage
    doc_coverage_pct, missing_docs_count = compute_doc_coverage(code, language)

    return {
        "file_name": file_name,
        "file_path": relative_path,
        "language": language,
        "lines": lines,
        "functions": analysis["functions"],
        "imports": analysis["imports"],
        "dead_code": dead_code,
        "code_smells": dead_code,
        "complexity_metrics": complexity_results,
        "cyclomatic_complexity": file_cyclomatic,
        "max_cyclomatic_complexity": file_max_cyclomatic,
        "time_complexity": file_time_complexity,
        "documentation_coverage": doc_coverage_pct,
        "undocumented_functions": missing_docs_count,
        "content": code,
        "is_code": True,
        "file_type": file_type,          # coarse: production/test/non_code
        "file_role": file_role,          # fine: utility/orchestrator/cli_parser/data_model/test
        "is_test": file_role == "test",  # Defect B: give the engine a real is_test signal
        "cohesion": cohesion,            # PHASE 2: single source of truth for size flagging
    }


# ==========================================================
# Parallel dispatch (Phase 6 / Chunk 5)
# ==========================================================
# The per-file structural pass is CPU-bound and embarrassingly
# parallel: _analyze_file_worker is a module-level, stateless,
# picklable worker (it constructs its own detectors), so it fans
# out across processes cleanly. We only parallelize ABOVE a
# threshold — pool startup (spawn on Windows especially) costs more
# than it saves on tiny repos. All knobs are env-driven so a
# container can tune them with no code change:
#
#   ANALYSIS_PARALLEL            "auto" (default) | "off"
#   ANALYSIS_MAX_WORKERS         int   (default = os.cpu_count())
#   ANALYSIS_PARALLEL_THRESHOLD  int   (default = 8 files to fan out)
#
# DETERMINISM CONTRACT: results are consumed in INPUT ORDER (both
# billiard.Pool.map and ProcessPoolExecutor.map preserve order), so
# the first-seen dedup in analyze_repository() is byte-identical to
# the old sequential loop. Parallelism must never change which
# duplicate wins or the order of files in the report.


def _resolve_worker_count(n_files: int) -> int:
    """How many workers to use for `n_files` (1 == run sequentially)."""
    mode = os.getenv("ANALYSIS_PARALLEL", "auto").strip().lower()
    if mode in ("off", "0", "false", "no", "sequential"):
        return 1

    try:
        threshold = int(os.getenv("ANALYSIS_PARALLEL_THRESHOLD", "8"))
    except ValueError:
        threshold = 8
    if n_files < max(threshold, 2):
        return 1

    try:
        configured = int(os.getenv("ANALYSIS_MAX_WORKERS", "0"))
    except ValueError:
        configured = 0
    max_workers = configured if configured > 0 else (os.cpu_count() or 1)
    return max(1, min(max_workers, n_files))


def _map_file_workers(worker_args: List) -> List:
    """Run _analyze_file_worker over worker_args, PRESERVING order.

    Pool preference: billiard.Pool (bundled with Celery, and the only
    pool safe to create INSIDE a Celery prefork worker, whose children
    are daemonic and reject a stdlib multiprocessing pool) -> stdlib
    ProcessPoolExecutor -> plain sequential map.

    A pool failure logs LOUDLY and then falls back. A *silent* drop to
    sequential would make the pass look parallel while running serial —
    the exact 'feature looks like it exists' failure this chunk is
    guarding against — so the fallback always announces itself.
    """
    n = len(worker_args)
    workers = _resolve_worker_count(n)

    if workers <= 1:
        return [_analyze_file_worker(a) for a in worker_args]

    # Preferred: billiard (Celery-safe nested pool) — but ONLY off Windows.
    # billiard.Pool is required *inside a Celery prefork worker* (whose daemonic
    # children reject a stdlib pool), which only ever runs in the Linux
    # container. On Windows its spawn bootstrap can abort the interpreter
    # outright — an uncatchable native crash, not an Exception the fallback
    # below could see — under pytest. Local Windows dev never runs a Celery
    # worker, so there we skip straight to ProcessPoolExecutor. (Before Celery
    # was a dependency billiard was simply absent, so this branch never ran and
    # the crash stayed hidden.)
    _BilliardPool = None
    if os.name != "nt":
        try:
            from billiard import Pool as _BilliardPool  # ships with celery
        except ImportError:
            _BilliardPool = None
    if _BilliardPool is not None:
        try:
            with _BilliardPool(processes=workers) as pool:
                return list(pool.map(_analyze_file_worker, worker_args))
        except Exception as e:  # noqa: BLE001 - fall through, but never silently
            print(f"[parallel] billiard pool failed ({e!r}); "
                  f"trying ProcessPoolExecutor")

    # Fallback: stdlib process pool (fine outside a Celery worker).
    try:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            return list(ex.map(_analyze_file_worker, worker_args))
    except Exception as e:  # noqa: BLE001
        print(f"[parallel] ProcessPoolExecutor failed ({e!r}); "
              f"falling back to SEQUENTIAL for {n} files")
        return [_analyze_file_worker(a) for a in worker_args]


# ==========================================================
# Repository Analyzer
# ==========================================================

class RepoAnalyzer:

    def __init__(self):
        self.dead_code_detector = DeadCodeDetector()
        self.complexity_analyzer = ComplexityAnalyzer()

    def analyze_repository(self, repo_path: str,
                           since_sha: str = None,
                           prior_files: List[Dict] = None) -> List[Dict]:

        repo_path = Path(repo_path)
        file_paths = []

        for root, dirs, files in os.walk(repo_path):
            dirs[:] = [d for d in dirs if d not in IGNORED_DIRECTORIES]
            for file in files:
                ext = os.path.splitext(file.lower())[1]
                if ext not in ALL_EXTENSIONS:
                    continue
                path = Path(root) / file
                file_paths.append(path)

        def _rel(path: Path) -> str:
            try:
                return str(path.relative_to(repo_path)).replace("\\", "/")
            except ValueError:
                return str(path).replace("\\", "/")

        # PHASE 6 (Chunk 5): incremental git-diff re-analysis. When a prior
        # scan's SHA + per-file results are supplied AND the diff is
        # computable, re-run the expensive per-file pass only on changed/new
        # files and reuse prior results for the rest. Falls back to a full
        # pass (logged, never silent) when the diff can't be computed. The
        # cross-file reduce below always runs over the FULL set, so an
        # unchanged file's cross-file verdict stays correct.
        changed = None
        reuse_by_path: Dict[str, Dict] = {}
        if since_sha and prior_files:
            changed = incremental.changed_files(str(repo_path), since_sha)
            if changed is None:
                print(f"[incremental] cannot diff since {str(since_sha)[:8]} "
                      f"-> full analysis")
            else:
                reuse_by_path = {f["file_path"]: f for f in prior_files
                                 if isinstance(f, dict) and "file_path" in f}

        if changed is None:
            # Full pass (default path — behaviour unchanged). PRESERVES INPUT
            # ORDER so the first-seen dedup below matches the old sequential loop.
            raw_results = _map_file_workers([(p, repo_path) for p in file_paths])
        else:
            # Incremental pass: analyze changed/new files, reuse the rest.
            rels = {p: _rel(p) for p in file_paths}
            to_analyze = [p for p in file_paths
                          if rels[p] in changed or rels[p] not in reuse_by_path]
            fresh = _map_file_workers([(p, repo_path) for p in to_analyze])
            fresh_by_path = {r["file_path"]: r for r in fresh if r}
            # Reassemble in walk order so output is identical to a full pass.
            raw_results = [fresh_by_path.get(rels[p]) or reuse_by_path.get(rels[p])
                           for p in file_paths]
            print(f"[incremental] re-analyzed {len(to_analyze)}, "
                  f"reused {len(file_paths) - len(to_analyze)} of "
                  f"{len(file_paths)} files")

        files_data = []
        seen_paths = set()

        for result in raw_results:
            if result:
                fp = result["file_path"]
                if fp not in seen_paths:
                    seen_paths.add(fp)
                    files_data.append(result)

        # Interprocedural dead-function detection (retires the file-level
        # name-bag). Keyed by file_path so each file gets exactly its own dead
        # functions, with dynamic-dispatch and entrypoint awareness.
        code_files = [f for f in files_data if f.get("is_code", True)]
        sources = {f["file_path"]: f.get("content", "") for f in code_files}
        dead_by_path = self.dead_code_detector.detect_repository_dead_functions(sources)

        for file in code_files:
            file["dead_code"]["unused_functions"] = dead_by_path.get(file["file_path"], [])

        print(f"Repository scan complete. {len(files_data)} files found ({len(code_files)} code files).")
        return files_data


def analyze_repository(repo_path: str, since_sha: str = None,
                       prior_files: List[Dict] = None):
    analyzer = RepoAnalyzer()
    return analyzer.analyze_repository(repo_path, since_sha=since_sha,
                                       prior_files=prior_files)