# ==========================================================
# File: ast_parser.py
# Location: backend/app/analysis
#
# Purpose
# ----------------------------------------------------------
# Parses Python source code using the built-in AST module
# and extracts structural information such as:
#
# • function definitions
# • async function definitions
# • imported modules
#
# This information is later used by the repository analysis
# and RAG indexing pipeline to understand code structure.
#
# AST (Abstract Syntax Tree) allows safe static analysis
# without executing the code.
# ==========================================================

import ast
from typing import Dict, List


# ==========================================================
# Main Parser Function
# ==========================================================
def parse_python_file(code: str) -> Dict[str, List[str]]:
    """
    Parse Python code and extract high-level structural elements.

    Parameters
    ----------
    code : str
        Raw Python source code.

    Returns
    -------
    Dict[str, List[str]]
        Dictionary containing:
        - functions : list of function names
        - imports   : list of imported modules
    """

    # ------------------------------------------------------
    # Attempt to parse the code into an AST
    # ------------------------------------------------------
    try:
        tree = ast.parse(code)
    except SyntaxError:
        # Invalid Python file should not crash the pipeline
        return {
            "functions": [],
            "imports": []
        }

    functions: List[str] = []
    imports: List[str] = []

    # ------------------------------------------------------
    # Walk through every node in the AST tree
    # ------------------------------------------------------
    for node in ast.walk(tree):

        # ---------------------------
        # Normal function definitions
        # ---------------------------
        if isinstance(node, ast.FunctionDef):
            functions.append(node.name)

        # ---------------------------
        # Async function definitions
        # ---------------------------
        elif isinstance(node, ast.AsyncFunctionDef):
            functions.append(node.name)

        # ---------------------------
        # Direct imports
        # Example:
        # import os
        # import numpy as np
        # ---------------------------
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)

        # ---------------------------
        # From imports
        # Example:
        # from os import path
        # ---------------------------
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)

    # ------------------------------------------------------
    # Remove duplicates while preserving order
    # ------------------------------------------------------
    functions = list(dict.fromkeys(functions))
    imports = list(dict.fromkeys(imports))

    return {
        "functions": functions,
        "imports": imports
    }