# ==========================================================
# File: security_analyzer.py
# Purpose: Detect common security vulnerabilities in code
# ==========================================================

import ast
from typing import List


class SecurityAnalyzer(ast.NodeVisitor):
    """
    AST-based security analyzer that detects
    common security vulnerabilities.
    """

    def __init__(self):

        self.issues: List[str] = []

        # credential-related variable names
        self.credential_keywords = {
            "password",
            "passwd",
            "secret",
            "api_key",
            "apikey",
            "token",
            "access_key",
            "private_key",
            "client_secret",
            "auth_token"
        }

    # ------------------------------------------------------
    # Dangerous function detection
    # ------------------------------------------------------

    def visit_Call(self, node):

        # ----------------------------------------------
        # Direct dangerous builtins
        # ----------------------------------------------

        if isinstance(node.func, ast.Name):

            name = node.func.id

            if name == "eval":
                self.issues.append(
                    "Use of eval() detected which may allow arbitrary code execution."
                )

            elif name == "exec":
                self.issues.append(
                    "Use of exec() detected which may allow execution of unsafe code."
                )

            elif name == "compile":
                self.issues.append(
                    "Use of compile() detected which may enable dynamic code execution."
                )

        # ----------------------------------------------
        # Attribute-based calls
        # ----------------------------------------------

        elif isinstance(node.func, ast.Attribute):

            attr = node.func.attr

            # os.system
            if attr == "system":
                self.issues.append(
                    "Use of os.system() detected which may allow command injection."
                )

            # subprocess commands
            if attr in {"Popen", "call", "run"}:
                self.issues.append(
                    "Use of subprocess without sanitization may allow command injection."
                )

            # unsafe deserialization
            if attr == "loads":

                if isinstance(node.func.value, ast.Name):

                    if node.func.value.id == "pickle":
                        self.issues.append(
                            "Use of pickle.loads() detected which may allow unsafe deserialization."
                        )

        # ----------------------------------------------
        # shell=True detection
        # ----------------------------------------------

        for keyword in node.keywords:

            if keyword.arg == "shell":

                if isinstance(keyword.value, ast.Constant):

                    if keyword.value.value is True:
                        self.issues.append(
                            "Use of shell=True detected which may allow command injection."
                        )

        self.generic_visit(node)

    # ------------------------------------------------------
    # Hardcoded credential detection
    # ------------------------------------------------------

    def visit_Assign(self, node):

        for target in node.targets:

            if isinstance(target, ast.Name):

                var_name = target.id.lower()

                if any(key in var_name for key in self.credential_keywords):

                    if isinstance(node.value, ast.Constant):

                        if isinstance(node.value.value, str):

                            self.issues.append(
                                f"Hardcoded credential detected in variable '{var_name}'."
                            )

        self.generic_visit(node)

    # ------------------------------------------------------
    # SQL Injection detection
    # ------------------------------------------------------

    def visit_BinOp(self, node):

        if isinstance(node.op, ast.Add):

            if isinstance(node.left, ast.Constant):

                if isinstance(node.left.value, str):

                    query = node.left.value.lower()

                    if any(q in query for q in ["select", "insert", "update", "delete"]):
                        self.issues.append(
                            "Possible SQL injection via string concatenation."
                        )

        self.generic_visit(node)

    # ------------------------------------------------------
    # f-string SQL detection
    # ------------------------------------------------------

    def visit_JoinedStr(self, node):

        for value in node.values:

            if isinstance(value, ast.Constant):

                text = str(value.value).lower()

                if any(q in text for q in ["select", "insert", "update", "delete"]):
                    self.issues.append(
                        "Possible SQL injection via formatted string query."
                    )

        self.generic_visit(node)


# ----------------------------------------------------------
# Public API
# ----------------------------------------------------------

def detect_security_issues(code: str) -> List[str]:
    """
    Analyze code and return detected security issues.
    """

    try:

        tree = ast.parse(code)

        analyzer = SecurityAnalyzer()

        analyzer.visit(tree)

        return analyzer.issues

    except Exception:
        return []