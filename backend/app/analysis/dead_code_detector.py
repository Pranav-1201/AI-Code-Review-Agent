# ==========================================================
# File: dead_code_detector.py
# Location: backend/app/analysis
#
# Purpose
# ----------------------------------------------------------
# Performs static dead code analysis on Python files.
#
# Detects:
# • Unused imports
# • Unused variables
# • Potentially unused functions (repo-level)
#
# This module works together with the call graph generator
# to identify functions that are defined but never invoked.
# ==========================================================

import ast
from typing import Dict, List, Set


class DeadCodeDetector:
    """
    Detects dead or unused code elements in Python source files.
    """

    # ======================================================
    # File-Level Analysis
    # ======================================================

    def analyze(self, code: str) -> Dict:

        try:
            tree = ast.parse(code)
        except SyntaxError:
            return {
                "imports": [],
                "functions": [],
                "unused_imports": [],
                "unused_variables": []
            }

        imports: List[str] = []
        functions: List[str] = []
        assigned_vars: List[str] = []
        used_names: Set[str] = set()

        for node in ast.walk(tree):

            # ----------------------------------------------
            # Detect Imports
            # ----------------------------------------------

            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)

            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    imports.append(alias.name)

            # ----------------------------------------------
            # Detect Function Definitions
            # ----------------------------------------------

            elif isinstance(node, ast.FunctionDef):
                functions.append(node.name)

            # ----------------------------------------------
            # Detect Variable Assignments
            # ----------------------------------------------

            elif isinstance(node, ast.Assign):
                for target in node.targets:

                    if isinstance(target, ast.Name):
                        assigned_vars.append(target.id)

                    elif isinstance(target, ast.Tuple):
                        for elt in target.elts:
                            if isinstance(elt, ast.Name):
                                assigned_vars.append(elt.id)

            # ----------------------------------------------
            # Detect Variable Usage
            # ----------------------------------------------

            elif isinstance(node, ast.Name):
                used_names.add(node.id)

        # --------------------------------------------------
        # Remove duplicates while preserving order
        # --------------------------------------------------

        imports = list(dict.fromkeys(imports))
        functions = list(dict.fromkeys(functions))
        assigned_vars = list(dict.fromkeys(assigned_vars))

        # --------------------------------------------------
        # Detect Unused Elements
        # --------------------------------------------------

        unused_imports = [i for i in imports if i not in used_names]
        unused_variables = [v for v in assigned_vars if v not in used_names]

        return {
            "imports": imports,
            "functions": functions,
            "unused_imports": unused_imports,
            "unused_variables": unused_variables
        }

    # ======================================================
    # Repository-Level Dead Function Detection
    # ======================================================

    def detect_repository_dead_functions(
        self,
        files_data: List[Dict],
        call_graph: Dict[str, List[str]]
    ) -> List[str]:
        """
        Identify functions that are defined in the repository
        but never called anywhere.

        Parameters
        ----------
        files_data : List[Dict]
            Data extracted from repository files containing
            function definitions.

        call_graph : Dict[str, List[str]]
            Mapping of file -> called functions.

        Returns
        -------
        List[str]
            Potentially unused functions.
        """

        defined_functions: Set[str] = set()
        called_functions: Set[str] = set()

        for file in files_data:
            defined_functions.update(file.get("functions", []))

        for file_calls in call_graph.values():
            called_functions.update(file_calls)

        unused_functions = list(defined_functions - called_functions)

        return unused_functions