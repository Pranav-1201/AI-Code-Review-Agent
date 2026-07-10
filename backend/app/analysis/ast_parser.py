# ==========================================================
# File: ast_parser.py
# Location: backend/app/analysis
#
# Purpose
# ----------------------------------------------------------
# Canonical entry point for turning Python source into an AST
# for this codebase, plus extraction of high-level structure:
#
# • function definitions
# • async function definitions
# • imported modules
#
# Phase 2 adds ParentTracker / attach_parents(): every node in
# a tree produced by parse_module() carries a `.parent` back-
# reference (the Module root's parent is None). Downstream
# analysis (security context classification, taint tracking)
# needs to walk UP the tree, which `ast` does not support on
# its own.
#
# AST allows safe static analysis without executing the code.
# ==========================================================

import ast
from typing import Dict, List, Optional


# ==========================================================
# Parent linkage
# ==========================================================

class ParentTracker(ast.NodeVisitor):
    """
    Attach a `.parent` attribute to every node in a tree.

    Must run BEFORE any analysis visitor that walks upward.
    The Module root keeps `.parent = None`.
    """

    def generic_visit(self, node: ast.AST) -> None:
        for child in ast.iter_child_nodes(node):
            child.parent = node  # type: ignore[attr-defined]
        super().generic_visit(node)


def attach_parents(tree: ast.AST) -> ast.AST:
    """
    Annotate `tree` in place with `.parent` back-references
    and return it. Idempotent.
    """
    tree.parent = None  # type: ignore[attr-defined]
    ParentTracker().visit(tree)
    return tree


def parse_module(code: str) -> Optional[ast.Module]:
    """
    Parse source into a parent-annotated AST.

    Returns None on SyntaxError so callers never crash the
    pipeline on an unparsable file. This is the single place
    the project should parse Python source for analysis.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None

    attach_parents(tree)
    return tree


def iter_parents(node: ast.AST):
    """Yield each ancestor of `node`, nearest first."""
    parent = getattr(node, "parent", None)
    while parent is not None:
        yield parent
        parent = getattr(parent, "parent", None)


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
    # Parse (parent-annotated). Invalid Python must not crash
    # the pipeline.
    # ------------------------------------------------------
    tree = parse_module(code)

    if tree is None:
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
