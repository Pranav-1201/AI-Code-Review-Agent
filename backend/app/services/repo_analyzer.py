# ==========================================================
# File: repo_analyzer.py
# Purpose: Repository scanning and structural analysis
# ==========================================================

import os
import ast
from pathlib import Path
from typing import List, Dict

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

        files_data = []

        for root, dirs, files in os.walk(repo_path):

            # remove ignored directories
            dirs[:] = [d for d in dirs if d not in IGNORED_DIRECTORIES]

            for file in files:

                if not file.endswith(SUPPORTED_EXTENSIONS):
                    continue

                path = Path(root) / file

                try:
                    code = path.read_text(encoding="utf-8", errors="ignore")
                except Exception as e:
                    print(f"Failed to read {path}: {e}")
                    continue

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

                dead_code = self.dead_code_detector.analyze(code)

                # ---------------------------------------------
                # Complexity Analysis
                # ---------------------------------------------

                complexity_results = []

                if file.endswith(".py"):

                    try:
                        tree = ast.parse(code)

                        for node in ast.walk(tree):
                            if isinstance(node, ast.FunctionDef):

                                metrics = self.complexity_analyzer.analyze_function(node)
                                metrics["function"] = node.name

                                complexity_results.append(metrics)

                    except Exception:
                        pass

                # ---------------------------------------------
                # Store file metadata
                # ---------------------------------------------

                files_data.append({
                    "file_name": file,
                    "file_path": str(path.relative_to(repo_path)),
                    "functions": analysis["functions"],
                    "imports": analysis["imports"],
                    "dead_code": dead_code,
                    "complexity_metrics": complexity_results,
                    "content": code
                })

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