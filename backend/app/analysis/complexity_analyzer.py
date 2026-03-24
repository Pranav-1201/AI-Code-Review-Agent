# ==========================================================
# File: complexity_analyzer.py
# Location: backend/app/analysis
#
# Purpose
# ----------------------------------------------------------
# Performs static complexity analysis of Python functions
# using the AST module.
#
# Metrics extracted:
# • Cyclomatic Complexity
# • Loop Nesting Depth
# • Branch Count
# • Recursion Detection
# • Estimated Time Complexity
# • Risk Level Classification
# • Hotspot Detection
# ==========================================================

import ast
from typing import Dict


class ComplexityAnalyzer(ast.NodeVisitor):
    """
    AST-based analyzer that computes complexity metrics
    for a given Python function.
    """

    # ======================================================
    # Initialization
    # ======================================================

    def __init__(self):
        self.reset_state()

    def reset_state(self):
        """Reset internal state before analyzing a function."""

        self.cyclomatic_complexity = 1

        # Tracks current nesting level of loops
        self.loop_depth = 0

        # Maximum observed loop nesting
        self.max_loop_depth = 0

        # Total loops encountered
        self.total_loops = 0

        self.branches = 0
        self.is_recursive = False
        self.current_function = None

        self.recursive_calls = 0
        self.divide_and_conquer = False

    # ======================================================
    # Decision Nodes
    # ======================================================

    def visit_If(self, node):
        self.cyclomatic_complexity += 1
        self.branches += 1
        self.generic_visit(node)

    def visit_Try(self, node):
        handlers = len(node.handlers)
        self.cyclomatic_complexity += handlers
        self.branches += handlers
        self.generic_visit(node)

    def visit_BoolOp(self, node):
        self.cyclomatic_complexity += len(node.values) - 1
        self.generic_visit(node)

    # ======================================================
    # Loop Handling
    # ======================================================

    def visit_For(self, node):
        self._enter_loop(node)

    def visit_While(self, node):
        self._enter_loop(node)

    def visit_AsyncFor(self, node):
        self._enter_loop(node)

    # Comprehensions (hidden loops)

    def visit_ListComp(self, node):
        self._enter_loop(node)

    def visit_SetComp(self, node):
        self._enter_loop(node)

    def visit_DictComp(self, node):
        self._enter_loop(node)

    def visit_GeneratorExp(self, node):
        self._enter_loop(node)

    def _enter_loop(self, node):

        self.cyclomatic_complexity += 1

        self.total_loops += 1

        self.loop_depth += 1

        if self.loop_depth > self.max_loop_depth:
            self.max_loop_depth = self.loop_depth

        self.generic_visit(node)

        self.loop_depth -= 1

    # ======================================================
    # Recursion Detection
    # ======================================================

    def visit_Call(self, node):

        if isinstance(node.func, ast.Name):

            if node.func.id == self.current_function:
                self.is_recursive = True
                self.recursive_calls += 1

        elif isinstance(node.func, ast.Attribute):

            if node.func.attr == self.current_function:
                self.is_recursive = True
                self.recursive_calls += 1

        self.generic_visit(node)

    # ======================================================
    # Divide & Conquer Detection
    # ======================================================

    def visit_Subscript(self, node):

        if isinstance(node.slice, ast.Slice):
            self.divide_and_conquer = True

        self.generic_visit(node)

    # ======================================================
    # Main Analysis Entry
    # ======================================================

    def analyze_function(self, node: ast.FunctionDef) -> Dict:

        self.reset_state()

        self.current_function = node.name

        self.visit(node)

        return {
            "cyclomatic_complexity": self.cyclomatic_complexity,
            "max_loop_depth": self.max_loop_depth,
            "total_loops": self.total_loops,
            "branches": self.branches,
            "time_complexity": self.estimate_time_complexity(),
            "recursive": self.is_recursive,
            "risk_level": self.get_risk_level(),
            "hotspot": self.is_hotspot()
        }

    # ======================================================
    # Time Complexity Estimation (Improved)
    # ======================================================

    def estimate_time_complexity(self) -> str:

        # Divide & conquer recursion
        if self.is_recursive and self.divide_and_conquer:
            return "O(n log n)"

        # Multiple recursion calls
        if self.is_recursive and self.recursive_calls > 1:
            return "O(2^n)"

        # Linear recursion
        if self.is_recursive:
            return "O(n)"

        depth = self.max_loop_depth

        # No loops
        if depth == 0:
            return "O(1)"

        # Single level loops
        if depth == 1:
            return "O(n)"

        # Nested loops
        if depth == 2:
            return "O(n^2)"

        if depth == 3:
            return "O(n^3)"

        return "O(n^k)"

    # ======================================================
    # Risk Classification
    # ======================================================

    def get_risk_level(self) -> str:

        c = self.cyclomatic_complexity

        if c <= 5:
            return "LOW"

        if c <= 10:
            return "MEDIUM"

        return "HIGH"

    # ======================================================
    # Hotspot Detection
    # ======================================================

    def is_hotspot(self) -> bool:

        return (
            self.cyclomatic_complexity > 10
            or self.max_loop_depth >= 3
            or self.is_recursive
        )