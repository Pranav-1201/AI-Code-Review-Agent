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
#
# This information is used by the AI code review system
# to identify risky or inefficient functions.
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
        self.loop_depth = 0
        self.max_loop_depth = 0
        self.branches = 0
        self.is_recursive = False
        self.current_function = None

    # ======================================================
    # Decision Nodes
    # ======================================================

    def visit_If(self, node):
        self.cyclomatic_complexity += 1
        self.branches += 1
        self.generic_visit(node)

    def visit_For(self, node):
        self._handle_loop(node)

    def visit_While(self, node):
        self._handle_loop(node)

    def visit_Try(self, node):
        handlers = len(node.handlers)
        self.cyclomatic_complexity += handlers
        self.branches += handlers
        self.generic_visit(node)

    def visit_BoolOp(self, node):
        """
        Handles logical operators (and/or).
        Each additional operand increases complexity.
        """
        self.cyclomatic_complexity += len(node.values) - 1
        self.generic_visit(node)

    # ======================================================
    # Loop Handling
    # ======================================================

    def _handle_loop(self, node):
        self.cyclomatic_complexity += 1

        self.loop_depth += 1
        self.max_loop_depth = max(self.max_loop_depth, self.loop_depth)

        self.generic_visit(node)

        self.loop_depth -= 1

    # ======================================================
    # Recursion Detection
    # ======================================================

    def visit_Call(self, node):

        # Case 1: direct recursion
        if isinstance(node.func, ast.Name):
            if node.func.id == self.current_function:
                self.is_recursive = True

        # Case 2: attribute recursion (self.func())
        elif isinstance(node.func, ast.Attribute):
            if node.func.attr == self.current_function:
                self.is_recursive = True

        self.generic_visit(node)

    # ======================================================
    # Main Analysis Entry
    # ======================================================

    def analyze_function(self, node: ast.FunctionDef) -> Dict:
        """
        Analyze a function AST node and return complexity metrics.
        """

        self.reset_state()
        self.current_function = node.name

        self.visit(node)

        return {
            "cyclomatic_complexity": self.cyclomatic_complexity,
            "max_loop_depth": self.max_loop_depth,
            "branches": self.branches,
            "time_complexity": self.estimate_time_complexity(),
            "recursive": self.is_recursive,
            "risk_level": self.get_risk_level(),
            "hotspot": self.is_hotspot()
        }

    # ======================================================
    # Time Complexity Estimation
    # ======================================================

    def estimate_time_complexity(self) -> str:
        """
        Estimate algorithmic time complexity based on loop depth.
        """

        depth = self.max_loop_depth

        if depth == 0:
            return "O(1)"
        if depth == 1:
            return "O(n)"
        if depth == 2:
            return "O(n^2)"
        if depth == 3:
            return "O(n^3)"

        return "O(n^k)"

    # ======================================================
    # Risk Classification
    # ======================================================

    def get_risk_level(self) -> str:
        """
        Classify function risk based on cyclomatic complexity.
        """

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
        """
        Detect potential performance or maintenance hotspots.
        """

        return (
            self.cyclomatic_complexity > 10
            or self.max_loop_depth >= 3
            or self.is_recursive
        )
    # ======================================================
    # Loop Depth Analysis
    # ======================================================
    import ast

    def get_loop_depth(node, depth=0):
        max_depth = depth

        for child in ast.iter_child_nodes(node):

            if isinstance(child, (ast.For, ast.While)):
                child_depth = get_loop_depth(child, depth + 1)
                max_depth = max(max_depth, child_depth)

            else:
                child_depth = get_loop_depth(child, depth)
                max_depth = max(max_depth, child_depth)

        return max_depth