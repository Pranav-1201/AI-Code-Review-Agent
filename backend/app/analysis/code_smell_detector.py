# ==========================================================
# File: code_smell_detector.py
# Location: backend/app/analysis
#
# Purpose
# ----------------------------------------------------------
# Performs static code quality analysis on Python functions
# using the AST module.
#
# The detector identifies several common code smells:
#
# • Long Function
# • Deep Nesting
# • Too Many Branches
# • God Function
# • Magic Numbers
#
# This information is used by the AI repository analysis
# pipeline to generate code review insights.
# ==========================================================

import ast
from typing import Dict, List


class CodeSmellDetector(ast.NodeVisitor):
    """
    AST visitor that analyzes a function node and extracts
    code quality metrics.
    """

    # ======================================================
    # Initialization
    # ======================================================

    def __init__(self):

        self.reset_state()

    # ======================================================
    # Reset state before analyzing a new function
    # ======================================================

    def reset_state(self):

        self.lines = 0
        self.branches = 0
        self.loop_depth = 0
        self.max_loop_depth = 0
        self.magic_numbers: List[int] = []
        self.smells: List[str] = []

    # ======================================================
    # Analyze a Function Node
    # ======================================================

    def analyze_function(self, node: ast.FunctionDef) -> Dict:

        self.reset_state()

        # Estimate line count
        if hasattr(node, "end_lineno"):
            self.lines = node.end_lineno - node.lineno
        else:
            self.lines = len(node.body)

        self.visit(node)

        self.detect_smells()

        return {
            "lines": self.lines,
            "branches": self.branches,
            "max_loop_depth": self.max_loop_depth,
            "magic_numbers": list(set(self.magic_numbers)),
            "code_smells": self.smells
        }

    # ======================================================
    # Branch Detection
    # ======================================================

    def visit_If(self, node):

        self.branches += 1
        self.generic_visit(node)

    def visit_Try(self, node):

        self.branches += 1
        self.generic_visit(node)

    # ======================================================
    # Loop Detection
    # ======================================================

    def visit_For(self, node):

        self.loop_depth += 1
        self.max_loop_depth = max(self.max_loop_depth, self.loop_depth)

        self.generic_visit(node)

        self.loop_depth -= 1

    def visit_While(self, node):

        self.loop_depth += 1
        self.max_loop_depth = max(self.max_loop_depth, self.loop_depth)

        self.generic_visit(node)

        self.loop_depth -= 1

    # ======================================================
    # Magic Number Detection
    # ======================================================

    def visit_Constant(self, node):

        if isinstance(node.value, (int, float)):

            if node.value not in (0, 1):
                self.magic_numbers.append(node.value)

        self.generic_visit(node)

    # ======================================================
    # Code Smell Rules
    # ======================================================

    def detect_smells(self):

        if self.lines > 20:
            self.smells.append("Long Function")

        if self.max_loop_depth >= 3:
            self.smells.append("Deep Nesting")

        if self.branches > 5:
            self.smells.append("Too Many Branches")

        if self.lines > 40 and self.branches > 5:
            self.smells.append("God Function")

        if len(self.magic_numbers) > 3:
            self.smells.append("Magic Numbers")