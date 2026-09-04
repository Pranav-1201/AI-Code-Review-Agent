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


# PHASE 1: Role-aware complexity thresholds
COMPLEXITY_THRESHOLDS: dict[str, dict[str, int]] = {
    'orchestrator': {'warn': 25, 'error': 40},
    'cli_parser':   {'warn': 18, 'error': 30},
    'utility':      {'warn': 10, 'error': 20},
    'data_model':   {'warn': 12, 'error': 22},
    'test':         {'warn': 5,  'error': 10},
}
_DEFAULT_ROLE = 'utility'



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

        # The function currently being measured. visit_FunctionDef descends
        # into this one and stops at any other, so a nested def is scored on
        # its own body rather than folded into its parent (B2).
        self._root = None

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

    # NOTE: Comprehensions (ListComp, SetComp, DictComp, GeneratorExp)
    # are intentionally NOT counted as loops. They are O(n) linear
    # operations and should not inflate nesting depth. Counting them
    # caused false O(n²) for files like logging.py where a list
    # comprehension inside a while loop was reported as depth-2.
    #
    # B2: that reasoning is about DEPTH, and it was silently applied to
    # CYCLOMATIC COMPLEXITY too, because both metrics share this visitor.
    # They are different questions. A comprehension is a loop and its
    # filter is a branch, so both are decision points under McCabe — and
    # skipping them was the whole of the measured 25-point shortfall
    # against radon on review_repository. The handlers below add to
    # complexity WITHOUT touching loop_depth, so the O(n^2) fix stands.

    def _visit_comprehension(self, node):
        for generator in node.generators:
            self.cyclomatic_complexity += 1 + len(generator.ifs)
            self.branches += len(generator.ifs)
        self.generic_visit(node)

    visit_ListComp = _visit_comprehension
    visit_SetComp = _visit_comprehension
    visit_DictComp = _visit_comprehension
    visit_GeneratorExp = _visit_comprehension

    def visit_IfExp(self, node):
        """A ternary is an `if` that happens to be an expression."""
        self.cyclomatic_complexity += 1
        self.branches += 1
        self.generic_visit(node)

    # B2: a nested def is its own function and is measured as one. Folding
    # its branches into the enclosing function made the enclosing function
    # read as more complex than its own body is — exactly the 7-point
    # over-count measured on analyze_dependencies, whose nested _add_dep
    # carries 7 decision points of its own. A lambda is NOT skipped:
    # it has no separate entry of its own, so its branches belong to the
    # function that wrote it, which is what radon does too.

    def _skip_nested_function(self, node):
        if node is self._root:
            self.generic_visit(node)

    visit_FunctionDef = _skip_nested_function
    visit_AsyncFunctionDef = _skip_nested_function

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

    def analyze_function(self, node: ast.FunctionDef, role: str = 'utility') -> Dict: # PHASE 1: role parameter

        self.reset_state()

        self.current_function = node.name
        self._root = node

        self.visit(node)

        return {
            "cyclomatic_complexity": self.cyclomatic_complexity,
            "max_loop_depth": self.max_loop_depth,
            "total_loops": self.total_loops,
            "branches": self.branches,
            "time_complexity": self.estimate_time_complexity(),
            "recursive": self.is_recursive,
            "risk_level": self.get_risk_level(self.cyclomatic_complexity, role=role), # PHASE 1: Thread role and cc
            "hotspot": self.is_hotspot(role=role) # PHASE 1: Thread role
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

    def get_risk_level(self, cc: int, role: str = 'utility') -> str: # PHASE 1: role parameter and lookup

        # PHASE 1: Use role-aware thresholds
        thresholds = COMPLEXITY_THRESHOLDS.get(role, COMPLEXITY_THRESHOLDS[_DEFAULT_ROLE])
        if cc >= thresholds['error']:
            return 'error'
        if cc >= thresholds['warn']:
            return 'warning'
        return 'ok'

    # ======================================================
    # Hotspot Detection
    # ======================================================

    def is_hotspot(self, role: str = 'utility') -> bool: # PHASE 1: role parameter

        return (
            self.get_risk_level(self.cyclomatic_complexity, role=role) == 'error' # PHASE 1: Use get_risk_level
            or self.max_loop_depth >= 3
            or self.is_recursive
        )