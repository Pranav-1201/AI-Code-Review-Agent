# ==========================================================
# File: dead_code_detector.py
# Location: backend/app/analysis
#
# Purpose
# ----------------------------------------------------------
# Static dead-code analysis for Python files.
#
# Detects:
# • Unused imports   (alias-aware — Fix F)
# • Unused variables
# • Unused functions (repo-level, via the interprocedural
#                     call graph — retires the name-bag)
#
# File-level unused-import detection and repository-level dead
# function detection both delegate to call_graph so there is a
# single, alias-aware, dispatch-aware source of truth.
# ==========================================================

import ast
from collections import defaultdict
from typing import Dict, List, Set

from backend.app.analysis.call_graph import (
    build_import_graph,
    detect_unused_imports,
    build_interprocedural_graph,
    find_dead_functions,
    _module_key,
)


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

            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)

            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    imports.append(alias.name)

            elif isinstance(node, ast.FunctionDef):
                functions.append(node.name)

            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        assigned_vars.append(target.id)
                    elif isinstance(target, ast.Tuple):
                        for elt in target.elts:
                            if isinstance(elt, ast.Name):
                                assigned_vars.append(elt.id)

            elif isinstance(node, ast.Name):
                used_names.add(node.id)

        imports = list(dict.fromkeys(imports))
        functions = list(dict.fromkeys(functions))
        assigned_vars = list(dict.fromkeys(assigned_vars))

        # --------------------------------------------------
        # Unused imports — ALIAS-AWARE (Fix F)
        # --------------------------------------------------
        # The old logic compared the imported dotted name against used
        # Name ids, so `import numpy as np` reported "numpy" as unused
        # even when `np` was used. Delegate to call_graph, which keys
        # usage on the BOUND name (alias, else the import leaf).
        edges = build_import_graph({"<file>": code}).get("<file>", [])
        unused_edges = detect_unused_imports(tree, edges, "<file>")
        unused_imports = [e.importee for e in unused_edges]

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
        sources: Dict[str, str],
    ) -> Dict[str, List[str]]:
        """
        Identify functions defined in the repository but never used, using
        the interprocedural call graph (function->function edges with
        qualified names, dynamic-dispatch and entrypoint awareness) instead
        of the old file-level name-bag set difference.

        Parameters
        ----------
        sources : Dict[str, str]
            Mapping of file_path -> source code for the repository's code files.

        Returns
        -------
        Dict[str, List[str]]
            file_path -> list of dead (unused) function names in that file.
            Conservative: framework entrypoints, dynamic-dispatch (NodeVisitor)
            methods, dunders, and callback-referenced functions are NOT reported.
        """
        graph = build_interprocedural_graph(sources)
        dead = find_dead_functions(graph)

        module_to_paths: Dict[str, List[str]] = defaultdict(list)
        for path in sources:
            module_to_paths[_module_key(path)].append(path)

        out: Dict[str, List[str]] = {path: [] for path in sources}
        for node in dead:
            for path in module_to_paths.get(node.module, []):
                out[path].append(node.name)
        return out
