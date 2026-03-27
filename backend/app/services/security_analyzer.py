# ==========================================================
# File: security_analyzer.py
# Purpose: Detect common security vulnerabilities in code
# ==========================================================

import ast
from typing import List, Dict


class SecurityAnalyzer(ast.NodeVisitor):
    """
    AST-based security analyzer that detects
    common security vulnerabilities.
    Returns structured issue objects with severity,
    description, recommendation, and line number.
    """

    def __init__(self):

        self.issues: List[Dict] = []

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
    # Helper to add structured issue
    # ------------------------------------------------------

    def _add_issue(self, severity: str, description: str, recommendation: str, line: int = 0, issue_type: str = "Vulnerability"):
        self.issues.append({
            "type": issue_type,
            "severity": severity,
            "description": description,
            "recommendation": recommendation,
            "line": line
        })

    # ------------------------------------------------------
    # Dangerous function detection
    # ------------------------------------------------------

    def visit_Call(self, node):

        line = getattr(node, "lineno", 0)

        # ----------------------------------------------
        # Direct dangerous builtins
        # ----------------------------------------------

        if isinstance(node.func, ast.Name):

            name = node.func.id

            if name == "eval":
                self._add_issue(
                    severity="Critical",
                    description="Use of eval() detected which may allow arbitrary code execution.",
                    recommendation="Replace eval() with ast.literal_eval() for safe parsing, or use a proper parser for the expected input format.",
                    line=line,
                    issue_type="Dangerous Function"
                )

            elif name == "exec":
                self._add_issue(
                    severity="Critical",
                    description="Use of exec() detected which may allow execution of unsafe code.",
                    recommendation="Avoid exec() entirely. Use importlib for dynamic imports, or a sandboxed environment if dynamic code execution is required.",
                    line=line,
                    issue_type="Dangerous Function"
                )

            elif name == "compile":
                self._add_issue(
                    severity="Medium",
                    description="Use of compile() detected which may enable dynamic code execution.",
                    recommendation="Ensure compile() input is not derived from user input. Consider using safer alternatives.",
                    line=line,
                    issue_type="Dangerous Function"
                )

        # ----------------------------------------------
        # Attribute-based calls
        # ----------------------------------------------

        elif isinstance(node.func, ast.Attribute):

            attr = node.func.attr

            # os.system
            if attr == "system":
                self._add_issue(
                    severity="High",
                    description="Use of os.system() detected which may allow command injection.",
                    recommendation="Use subprocess.run() with a list of arguments instead of os.system() to prevent shell injection.",
                    line=line,
                    issue_type="Command Injection"
                )

            # subprocess commands
            if attr in {"Popen", "call", "run"}:
                self._add_issue(
                    severity="Medium",
                    description="Use of subprocess without sanitization may allow command injection.",
                    recommendation="Ensure arguments are passed as a list (not a string), avoid shell=True, and validate all inputs.",
                    line=line,
                    issue_type="Command Injection"
                )

            # unsafe deserialization
            if attr == "loads":

                if isinstance(node.func.value, ast.Name):

                    if node.func.value.id == "pickle":
                        self._add_issue(
                            severity="Critical",
                            description="Use of pickle.loads() detected which may allow unsafe deserialization and remote code execution.",
                            recommendation="Use json.loads() for data serialization, or implement HMAC validation before unpickling.",
                            line=line,
                            issue_type="Unsafe Deserialization"
                        )

                    elif node.func.value.id == "yaml":
                        self._add_issue(
                            severity="High",
                            description="Use of yaml.loads() detected which may allow unsafe deserialization.",
                            recommendation="Use yaml.safe_load() instead of yaml.load() to prevent arbitrary code execution.",
                            line=line,
                            issue_type="Unsafe Deserialization"
                        )

        # ----------------------------------------------
        # shell=True detection
        # ----------------------------------------------

        for keyword in node.keywords:

            if keyword.arg == "shell":

                if isinstance(keyword.value, ast.Constant):

                    if keyword.value.value is True:
                        self._add_issue(
                            severity="High",
                            description="Use of shell=True detected which may allow command injection.",
                            recommendation="Remove shell=True and pass command arguments as a list to subprocess.",
                            line=line,
                            issue_type="Command Injection"
                        )

            # detect verify=False in requests
            if keyword.arg == "verify":

                if isinstance(keyword.value, ast.Constant):

                    if keyword.value.value is False:
                        self._add_issue(
                            severity="Medium",
                            description="SSL verification disabled (verify=False) which allows man-in-the-middle attacks.",
                            recommendation="Enable SSL verification by removing verify=False or setting verify=True.",
                            line=line,
                            issue_type="Insecure Configuration"
                        )

        self.generic_visit(node)

    # ------------------------------------------------------
    # Hardcoded credential detection
    # ------------------------------------------------------

    def visit_Assign(self, node):

        line = getattr(node, "lineno", 0)

        for target in node.targets:

            if isinstance(target, ast.Name):

                var_name = target.id.lower()

                if any(key in var_name for key in self.credential_keywords):

                    if isinstance(node.value, ast.Constant):

                        if isinstance(node.value.value, str) and len(node.value.value) > 0:

                            self._add_issue(
                                severity="High",
                                description=f"Hardcoded credential detected in variable '{target.id}'.",
                                recommendation=f"Move the value of '{target.id}' to environment variables or a secrets manager (e.g., dotenv, AWS Secrets Manager).",
                                line=line,
                                issue_type="Hardcoded Credential"
                            )

        self.generic_visit(node)

    # ------------------------------------------------------
    # SQL Injection detection
    # ------------------------------------------------------

    def visit_BinOp(self, node):

        line = getattr(node, "lineno", 0)

        if isinstance(node.op, ast.Add):

            if isinstance(node.left, ast.Constant):

                if isinstance(node.left.value, str):

                    query = node.left.value.lower()

                    if any(q in query for q in ["select", "insert", "update", "delete"]):
                        self._add_issue(
                            severity="High",
                            description="Possible SQL injection via string concatenation.",
                            recommendation="Use parameterized queries or an ORM (e.g., SQLAlchemy) instead of string concatenation for SQL.",
                            line=line,
                            issue_type="SQL Injection"
                        )

        self.generic_visit(node)

    # ------------------------------------------------------
    # f-string SQL detection
    # ------------------------------------------------------

    def visit_JoinedStr(self, node):

        line = getattr(node, "lineno", 0)

        for value in node.values:

            if isinstance(value, ast.Constant):

                text = str(value.value).lower()

                if any(q in text for q in ["select", "insert", "update", "delete"]):
                    self._add_issue(
                        severity="High",
                        description="Possible SQL injection via formatted string query.",
                        recommendation="Use parameterized queries instead of f-strings for SQL. ORMs like SQLAlchemy provide safe query builders.",
                        line=line,
                        issue_type="SQL Injection"
                    )

        self.generic_visit(node)


# ----------------------------------------------------------
# Public API
# ----------------------------------------------------------

def detect_security_issues(code: str) -> List[Dict]:
    """
    Analyze code and return detected security issues
    as structured dictionaries.

    Each issue contains:
        type, severity, description, recommendation, line
    """

    try:

        tree = ast.parse(code)

        analyzer = SecurityAnalyzer()

        analyzer.visit(tree)

        return analyzer.issues

    except Exception:
        return []