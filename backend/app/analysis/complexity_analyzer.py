import ast


class ComplexityAnalyzer(ast.NodeVisitor):

    def __init__(self):
        self.cyclomatic_complexity = 1
        self.loop_depth = 0
        self.max_loop_depth = 0
        self.branches = 0
        self.is_recursive = False
        self.current_function = None

    # -----------------------------
    # Decision Nodes
    # -----------------------------

    def visit_If(self, node):
        self.cyclomatic_complexity += 1
        self.branches += 1
        self.generic_visit(node)

    def visit_For(self, node):
        self.cyclomatic_complexity += 1
        self.loop_depth += 1
        self.max_loop_depth = max(self.max_loop_depth, self.loop_depth)

        self.generic_visit(node)

        self.loop_depth -= 1

    def visit_While(self, node):
        self.cyclomatic_complexity += 1
        self.loop_depth += 1
        self.max_loop_depth = max(self.max_loop_depth, self.loop_depth)

        self.generic_visit(node)

        self.loop_depth -= 1

    def visit_Try(self, node):
        self.cyclomatic_complexity += len(node.handlers)
        self.branches += len(node.handlers)

        self.generic_visit(node)

    # -----------------------------
    # Detect recursion
    # -----------------------------

    def visit_Call(self, node):

        if isinstance(node.func, ast.Name):
            if node.func.id == self.current_function:
                self.is_recursive = True

        self.generic_visit(node)

    # -----------------------------
    # Analyze Function
    # -----------------------------

    def analyze_function(self, node):

        self.cyclomatic_complexity = 1
        self.loop_depth = 0
        self.max_loop_depth = 0
        self.branches = 0
        self.is_recursive = False
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

    # -----------------------------
    # Time Complexity Estimation
    # -----------------------------

    def estimate_time_complexity(self):

        depth = self.max_loop_depth

        if depth == 0:
            return "O(1)"
        elif depth == 1:
            return "O(n)"
        elif depth == 2:
            return "O(n²)"
        elif depth == 3:
            return "O(n³)"
        else:
            return "O(n^k)"

    # -----------------------------
    # Risk Classification
    # -----------------------------

    def get_risk_level(self):

        c = self.cyclomatic_complexity

        if c <= 5:
            return "LOW"
        elif c <= 10:
            return "MEDIUM"
        else:
            return "HIGH"

    # -----------------------------
    # Hotspot Detection
    # -----------------------------

    def is_hotspot(self):

        if self.cyclomatic_complexity > 10:
            return True

        if self.max_loop_depth >= 3:
            return True

        if self.is_recursive:
            return True

        return False