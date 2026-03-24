import ast


class CodeSmellDetector(ast.NodeVisitor):

    def __init__(self):

        self.lines = 0
        self.branches = 0
        self.loop_depth = 0
        self.max_loop_depth = 0
        self.magic_numbers = []
        self.smells = []

    # -----------------------------
    # Count Lines
    # -----------------------------

    def analyze_function(self, node):

        self.lines = len(node.body)
        self.branches = 0
        self.loop_depth = 0
        self.max_loop_depth = 0
        self.magic_numbers = []
        self.smells = []

        self.visit(node)

        self.detect_smells()

        return {
            "lines": self.lines,
            "branches": self.branches,
            "max_loop_depth": self.max_loop_depth,
            "magic_numbers": self.magic_numbers,
            "code_smells": self.smells
        }

    # -----------------------------
    # Decision Nodes
    # -----------------------------

    def visit_If(self, node):

        self.branches += 1
        self.generic_visit(node)

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

    # -----------------------------
    # Magic Number Detection
    # -----------------------------

    def visit_Constant(self, node):

        if isinstance(node.value, (int, float)):

            if node.value not in [0, 1]:
                self.magic_numbers.append(node.value)

        self.generic_visit(node)

    # -----------------------------
    # Detect Smells
    # -----------------------------

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