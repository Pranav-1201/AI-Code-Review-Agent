# ==========================================================
# File: repo_analyzer.py
# Purpose: Repository scanning and structural analysis
# ==========================================================

import os
import ast
from pathlib import Path
from typing import List, Dict
from multiprocessing import Pool, cpu_count

from backend.app.analysis.ast_parser import parse_python_file
from backend.app.analysis.dead_code_detector import DeadCodeDetector
from backend.app.analysis.call_graph import build_call_graph
from backend.app.analysis.complexity_analyzer import ComplexityAnalyzer


SUPPORTED_EXTENSIONS = (
    ".py",
    ".js",
    ".cpp",
    ".c",
    ".java"
)

IGNORED_DIRECTORIES = {
    ".git",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
    "docs",
    "tests"
}

# ----------------------------------------------------------
# Language Detection
# ----------------------------------------------------------

def detect_language(filename: str):

    if filename.endswith(".py"):
        return "Python"
    if filename.endswith(".js"):
        return "JavaScript"
    if filename.endswith(".cpp"):
        return "C++"
    if filename.endswith(".java"):
        return "Java"
    if filename.endswith(".ts") or filename.endswith(".tsx"):
        return "TypeScript"

    return "Unknown"


def count_lines(code: str):
    return len(code.splitlines())


# ----------------------------------------------------------
# Documentation Coverage (Python)
# ----------------------------------------------------------

def compute_doc_coverage(code: str, language: str) -> float:
    """
    Compute documentation coverage as the percentage
    of functions/classes that have docstrings.

    Returns a value between 0 and 100.
    """

    if language != "Python":
        return 0.0

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return 0.0

    total_definitions = 0
    documented_definitions = 0

    for node in ast.walk(tree):

        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):

            total_definitions += 1

            # Check for docstring (first statement is a string constant)
            if (node.body
                and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)):

                documented_definitions += 1

    if total_definitions == 0:
        return 0.0

    return round((documented_definitions / total_definitions) * 100, 1)


# ----------------------------------------------------------
# Worker Function (Multiprocessing)
# ----------------------------------------------------------

def _analyze_file_worker(args):

    path, repo_path = args

    dead_code_detector = DeadCodeDetector()
    complexity_analyzer = ComplexityAnalyzer()

    file_name = path.name
    language = detect_language(file_name)

    if path.stat().st_size > 200000:  # 200 KB
        return None
    
    try:
        code = path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        print(f"Failed to read {path}: {e}")
        return None

    # --------------------------------------------------
    # Skip empty or trivial files (Phase 3 fix)
    # --------------------------------------------------

    lines_clean = [l for l in code.splitlines() if l.strip()]

    if len(lines_clean) < 2:
        return None

    language = detect_language(file_name)
    lines = count_lines(code)

    analysis = {"functions": [], "imports": []}

    # ---------------------------------------------
    # AST Parsing (Python only)
    # ---------------------------------------------

    if file_name.endswith(".py"):
        try:
            analysis = parse_python_file(code)
        except Exception:
            pass

    # ---------------------------------------------
    # Dead Code Detection
    # ---------------------------------------------

    dead_code = dead_code_detector.analyze(code)

    # ---------------------------------------------
    # Complexity Analysis
    # ---------------------------------------------

    complexity_results = []

    if file_name.endswith(".py"):

        try:

            tree = ast.parse(code)

            for node in ast.walk(tree):

                if isinstance(node, ast.FunctionDef):

                    metrics = complexity_analyzer.analyze_function(node)
                    metrics["function"] = node.name

                    complexity_results.append(metrics)

        except Exception:
            pass

    # ---------------------------------------------
    # Aggregate Cyclomatic Complexity (file-level)
    # ---------------------------------------------

    file_cyclomatic = 0
    file_time_complexity = "O(1)"

    if complexity_results:
        # Sum of all function complexities
        file_cyclomatic = sum(
            fn.get("cyclomatic_complexity", 0)
            for fn in complexity_results
        )

        # Worst-case time complexity across functions
        max_depth = max(
            fn.get("max_loop_depth", 0)
            for fn in complexity_results
        )

        # Use the analyzer's complexity estimation logic
        if max_depth == 0:
            file_time_complexity = "O(1)"
        elif max_depth == 1:
            file_time_complexity = "O(n)"
        elif max_depth == 2:
            file_time_complexity = "O(n^2)"
        elif max_depth == 3:
            file_time_complexity = "O(n^3)"
        else:
            file_time_complexity = "O(n^k)"

        # Check for recursive functions
        has_recursive = any(fn.get("recursive", False) for fn in complexity_results)
        if has_recursive and max_depth <= 1:
            file_time_complexity = "O(n)"

    # ---------------------------------------------
    # Documentation Coverage
    # ---------------------------------------------

    doc_coverage = compute_doc_coverage(code, language)

    # ---------------------------------------------
    # Return File Metadata
    # ---------------------------------------------

    # Use relative path for unique identification
    try:
        relative_path = str(path.relative_to(repo_path))
    except ValueError:
        relative_path = str(path)

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
        "time_complexity": file_time_complexity,
        "documentation_coverage": doc_coverage,
        "content": code
    }


# ==========================================================
# Repository Analyzer
# ==========================================================

class RepoAnalyzer:

    def __init__(self):
        self.dead_code_detector = DeadCodeDetector()
        self.complexity_analyzer = ComplexityAnalyzer()

    # ------------------------------------------------------
    # Main Repository Analysis
    # ------------------------------------------------------

    def analyze_repository(self, repo_path: str) -> List[Dict]:

        repo_path = Path(repo_path)

        file_paths = []

        # --------------------------------------------------
        # Collect files
        # --------------------------------------------------

        for root, dirs, files in os.walk(repo_path):

            dirs[:] = [d for d in dirs if d not in IGNORED_DIRECTORIES]

            for file in files:

                if not file.lower().endswith(SUPPORTED_EXTENSIONS):
                    continue

                path = Path(root) / file
                file_paths.append(path)

        # --------------------------------------------------
        # Multiprocessing file analysis
        # --------------------------------------------------

        worker_args = [(path, repo_path) for path in file_paths]

        files_data = []

        for args in worker_args:
                result = _analyze_file_worker(args)
                if result:
                    files_data.append(result)

        # --------------------------------------------------
        # Build Call Graph
        # --------------------------------------------------

        call_graph = build_call_graph(files_data)

        # --------------------------------------------------
        # Detect repository-level dead functions
        # --------------------------------------------------

        unused_functions = self.dead_code_detector.detect_repository_dead_functions(
            files_data,
            call_graph
        )

        for file in files_data:

            file["dead_code"]["unused_functions"] = [
                f for f in file["functions"] if f in unused_functions
            ]

        print(f"Repository scan complete. {len(files_data)} files found.")

        return files_data


# ----------------------------------------------------------
# Wrapper Function
# ----------------------------------------------------------

def analyze_repository(repo_path: str):

    analyzer = RepoAnalyzer()
    return analyzer.analyze_repository(repo_path)