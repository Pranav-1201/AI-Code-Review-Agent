# ==========================================================
# File: repo_analyzer.py
# Purpose: Repository scanning and structural analysis
# ==========================================================

import os
import ast
from pathlib import Path
from typing import List, Dict

from backend.app.analysis.ast_parser import parse_python_file
from backend.app.analysis.dead_code_detector import DeadCodeDetector
from backend.app.analysis.call_graph import build_call_graph
from backend.app.analysis.complexity_analyzer import ComplexityAnalyzer


# ----------------------------------------------------------
# Supported extensions — restricted to Java, C++, JS/TS, Python
# ----------------------------------------------------------

CODE_EXTENSIONS = (
    ".py", ".js", ".jsx", ".ts", ".tsx",
    ".java", ".cpp", ".c", ".h", ".hpp", ".cc", ".cxx"
)

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

def is_test_file(file_path: str) -> bool:
    """
    Determine whether a file is a test file based on its path.
    Test files are excluded from production scoring but remain
    visible in the UI.

    Matches:
      - Any file inside a /tests/ or /test/ directory
      - Files named test_*.py or *_test.py
      - conftest.py (pytest fixtures)
    """
    normalized = file_path.replace("\\", "/").lower()
    parts = normalized.split("/")

    # Check if any directory component is 'tests' or 'test'
    if "tests" in parts or "test" in parts:
        return True

    # Check filename patterns
    basename = parts[-1] if parts else ""
    if basename.startswith("test_") and basename.endswith(".py"):
        return True
    if basename.endswith("_test.py"):
        return True
    if basename == "conftest.py":
        return True

    return False


# ----------------------------------------------------------
# Documentation Coverage (Python)
# ----------------------------------------------------------

def compute_doc_coverage(code: str, language: str) -> float:
    if language != "Python":
        return 0.0

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return 0.0

    total = 0
    documented = 0

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            total += 1
            if (node.body
                and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)):
                documented += 1

    if total == 0:
        return 0.0

    return round((documented / total) * 100, 1)


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
            "is_test": False,
            "file_type": "non_code",
        }

    # --------------------------------------------------
    # Code files: full analysis
    # --------------------------------------------------
    analysis = {"functions": [], "imports": []}

    if ext == ".py":
        try:
            analysis = parse_python_file(code)
        except Exception:
            pass

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
                    metrics = complexity_analyzer.analyze_function(node)
                    metrics["function"] = node.name
                    complexity_results.append(metrics)
        except Exception:
            pass

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

    # Documentation coverage
    doc_coverage = compute_doc_coverage(code, language)

    # Test file classification
    test_flag = is_test_file(relative_path)

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
        "documentation_coverage": doc_coverage,
        "content": code,
        "is_code": True,
        "is_test": test_flag,
        "file_type": "test" if test_flag else "production",
    }


# ==========================================================
# Repository Analyzer
# ==========================================================

class RepoAnalyzer:

    def __init__(self):
        self.dead_code_detector = DeadCodeDetector()
        self.complexity_analyzer = ComplexityAnalyzer()

    def analyze_repository(self, repo_path: str) -> List[Dict]:

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

        worker_args = [(path, repo_path) for path in file_paths]
        files_data = []
        seen_paths = set()

        for args in worker_args:
            result = _analyze_file_worker(args)
            if result:
                fp = result["file_path"]
                if fp not in seen_paths:
                    seen_paths.add(fp)
                    files_data.append(result)

        # Build call graph (code files only)
        code_files = [f for f in files_data if f.get("is_code", True)]
        call_graph = build_call_graph(code_files)

        # Dead function detection
        unused_functions = self.dead_code_detector.detect_repository_dead_functions(
            code_files, call_graph
        )

        for file in code_files:
            file["dead_code"]["unused_functions"] = [
                f for f in file.get("functions", []) if f in unused_functions
            ]

        print(f"Repository scan complete. {len(files_data)} files found ({len(code_files)} code files).")
        return files_data


def analyze_repository(repo_path: str):
    analyzer = RepoAnalyzer()
    return analyzer.analyze_repository(repo_path)