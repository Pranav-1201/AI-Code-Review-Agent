# ==========================================================
# File: repo_analyzer.py
# Purpose: Repository scanning and structural analysis
# ==========================================================

import os
import ast
from pathlib import Path
from typing import List, Dict
from multiprocessing import Pool, cpu_count

from app.analysis.ast_parser import parse_python_file
from app.analysis.dead_code_detector import DeadCodeDetector
from app.analysis.call_graph import build_call_graph
from app.analysis.complexity_analyzer import ComplexityAnalyzer


SUPPORTED_EXTENSIONS = (".py", ".cpp", ".js", ".java")

# directories that should never be scanned
IGNORED_DIRECTORIES = {
    ".git",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv"
}


# ----------------------------------------------------------
# Worker Function (must be top-level for multiprocessing)
# ----------------------------------------------------------

def _analyze_file_worker(args):

    path, repo_path = args

    dead_code_detector = DeadCodeDetector()
    complexity_analyzer = ComplexityAnalyzer()

    file = path.name

    try:
        code = path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        print(f"Failed to read {path}: {e}")
        return None

    # ---------------------------------------------
    # AST Parsing (Python only)
    # ---------------------------------------------

    analysis = {"functions": [], "imports": []}

    if file.endswith(".py"):
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

    if file.endswith(".py"):

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
    # Return file metadata
    # ---------------------------------------------

    return {
        "file_name": file,
        "file_path": str(path.relative_to(repo_path)),
        "functions": analysis["functions"],
        "imports": analysis["imports"],
        "dead_code": dead_code,
        "complexity_metrics": complexity_results,
        "content": code
    }


class RepoAnalyzer:
    """
    Scans a repository and extracts structural metadata.
    """

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
        # Scan repository and collect files
        # --------------------------------------------------

        for root, dirs, files in os.walk(repo_path):

            # remove ignored directories
            dirs[:] = [d for d in dirs if d not in IGNORED_DIRECTORIES]

            for file in files:

                if not file.endswith(SUPPORTED_EXTENSIONS):
                    continue

                path = Path(root) / file
                file_paths.append(path)

        # --------------------------------------------------
        # Parallel file analysis
        # --------------------------------------------------

        files_data = []

        worker_args = [(path, repo_path) for path in file_paths]

        num_workers = max(1, cpu_count() - 1)

        try:

            with Pool(processes=num_workers) as pool:
                results = pool.map(_analyze_file_worker, worker_args)

            files_data = [r for r in results if r is not None]

        except Exception as e:
            print(f"[RepoAnalyzer Warning] Multiprocessing failed, falling back to sequential: {e}")

            # fallback to sequential
            for args in worker_args:
                result = _analyze_file_worker(args)
                if result:
                    files_data.append(result)

        # --------------------------------------------------
        # Build Repository Call Graph
        # --------------------------------------------------

        call_graph = build_call_graph(files_data)

        # --------------------------------------------------
        # Repository-level Dead Functions
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
# Wrapper for compatibility with existing tests
# ----------------------------------------------------------

def analyze_repository(repo_path: str):
    analyzer = RepoAnalyzer()
    return analyzer.analyze_repository(repo_path)