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

    def __init__(self, is_test: bool = False, file_path: str = ""):

        self.issues: List[Dict] = []
        self.is_test = is_test
        self.file_path = file_path.replace("\\", "/").lower()

        # Framework-aware file patterns where eval/exec/compile
        # are expected and controlled (not user-input driven)
        self._is_framework_context = any(
            pat in self.file_path
            for pat in ("cli.py", "config.py", "__init__.py", "app.py",
                        "factory", "loader", "runner", "commands")
        )

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
        
        # Determine why_it_matters dynamically
        why_it_matters = "This represents a generic security risk or code smell that could weaken application stability."
        if "Hardcoded credentials" in description:
            why_it_matters = "Exposing secrets in code can lead to credential theft and complete system compromise."
        elif "Dangerous Function" in issue_type:
            why_it_matters = "Executing arbitrary strings or unvalidated input can allow attackers to hijack the application (RCE)."
        elif "Shell Injection" in issue_type or "Command" in issue_type:
            why_it_matters = "Running external commands with untrusted input can let attackers run unauthorized utilities on the server."
        elif "Cryptographic" in issue_type or "MD5" in description or "SHA1" in description:
            why_it_matters = "Weak hashing algorithms can be easily reversed using dictionary attacks or rainbow tables."
            
        # Determine confidence score deterministically
        confidence = 0.8
        if "Hardcoded" in description:
            confidence = 0.6  # Might be a test literal
        elif "[Intentional Pattern]" in description:
            confidence = 0.95
        elif "shell=True" in description:
            confidence = 0.99
        elif "eval(" in description or "exec(" in description:
            confidence = 0.90

        self.issues.append({
            "type": issue_type,
            "severity": severity,
            "description": description,
            "recommendation": recommendation,
            "line": line,
            "why_it_matters": why_it_matters,
            "how_to_fix": recommendation,
            "confidence": confidence,
            "snippet": f"Line {line} indicates: {issue_type}"  # Simplified without full tree mapping
        })

    # ------------------------------------------------------
    # Context-aware reasoning for [Intentional Pattern]
    # Maps file paths to human-readable explanations of
    # WHY a dangerous function is expected in that context.
    # ------------------------------------------------------

    def _get_framework_reason(self, func_name: str) -> str:
        fp = self.file_path.lower()
        if "config" in fp:
            if func_name == "exec":
                return "config file loading — executes Python config files from a trusted path"
            elif func_name == "compile":
                return "config file loading — compiles Python config source before exec"
            return "configuration subsystem — processes trusted operator-provided config"
        elif "cli" in fp:
            if func_name == "eval":
                return "CLI shell/REPL — replicates standard Python interactive interpreter behavior"
            elif func_name == "compile":
                return "CLI startup — compiles PYTHONSTARTUP file for shell context"
            return "CLI command framework — operates on operator-controlled inputs"
        elif "app" in fp:
            return "application factory — framework-level initialization code"
        elif "__init__" in fp:
            return "package initialization — framework bootstrap code"
        return "framework-level code — operates on trusted internal data"

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
                is_constant_arg = len(node.args) > 0 and isinstance(node.args[0], ast.Constant)
                if self._is_framework_context:
                    severity = "Low"
                    reason = self._get_framework_reason("eval")
                    desc = f"[Intentional Pattern] eval() in {reason}. Operator-level risk only — not user-input driven."
                else:
                    severity = "Low" if is_constant_arg else "Critical"
                    desc = "Use of eval() detected which may allow arbitrary code execution."
                
                self._add_issue(
                    severity=severity,
                    description=desc,
                    recommendation="Replace eval() with ast.literal_eval() for safe parsing, or use a proper parser for the expected input format.",
                    line=line,
                    issue_type="Dangerous Function"
                )

            elif name == "exec":
                is_constant_arg = len(node.args) > 0 and isinstance(node.args[0], ast.Constant)
                if self._is_framework_context:
                    severity = "Low"
                    reason = self._get_framework_reason("exec")
                    desc = f"[Intentional Pattern] exec() in {reason}. Operator-level risk only — not user-input driven."
                else:
                    severity = "Low" if is_constant_arg else "Critical"
                    desc = "Use of exec() detected which may allow execution of unsafe code."

                self._add_issue(
                    severity=severity,
                    description=desc,
                    recommendation="Avoid exec() entirely. Use importlib for dynamic imports, or a sandboxed environment.",
                    line=line,
                    issue_type="Dangerous Function"
                )

            elif name == "compile":
                is_constant_arg = len(node.args) > 0 and isinstance(node.args[0], ast.Constant)
                if self._is_framework_context:
                    severity = "Info"
                    reason = self._get_framework_reason("compile")
                    desc = f"[Intentional Pattern] compile() in {reason}. Low risk — typically pairs with exec/eval."
                else:
                    severity = "Low" if is_constant_arg else "Medium"
                    desc = "Use of compile() detected which may enable dynamic code execution."

                self._add_issue(
                    severity=severity,
                    description=desc,
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
                is_constant_arg = len(node.args) > 0 and isinstance(node.args[0], (ast.List, ast.Tuple, ast.Constant))
                severity = "Low" if (self.is_test or is_constant_arg) else "Medium"
                self._add_issue(
                    severity=severity,
                    description="[Verify Context] Use of subprocess without sanitization may allow command injection.",
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

        if self.is_test:
            self.generic_visit(node)
            return

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

    # ------------------------------------------------------
    # Weak hash detection
    # ------------------------------------------------------

    def visit_Attribute(self, node):

        line = getattr(node, "lineno", 0)

        if isinstance(node.value, ast.Name) and node.value.id == "hashlib":
            if node.attr in ("md5", "sha1"):
                self._add_issue(
                    severity="Medium",
                    description=f"Use of weak hash algorithm hashlib.{node.attr}() detected.",
                    recommendation="Use hashlib.sha256() or hashlib.sha3_256() for secure hashing. MD5 and SHA1 are vulnerable to collision attacks.",
                    line=line,
                    issue_type="Weak Cryptography"
                )

        # tempfile.mktemp() race condition
        if isinstance(node.value, ast.Name) and node.value.id == "tempfile":
            if node.attr == "mktemp":
                self._add_issue(
                    severity="Medium",
                    description="Use of tempfile.mktemp() detected which is vulnerable to race conditions.",
                    recommendation="Use tempfile.mkstemp() or tempfile.NamedTemporaryFile() instead for secure temporary file creation.",
                    line=line,
                    issue_type="Race Condition"
                )

        self.generic_visit(node)

    # ------------------------------------------------------
    # Wildcard import detection
    # ------------------------------------------------------

    def visit_ImportFrom(self, node):

        line = getattr(node, "lineno", 0)

        if node.names and any(alias.name == "*" for alias in node.names):
            self._add_issue(
                severity="Low",
                description=f"Wildcard import 'from {node.module} import *' may introduce unexpected names into namespace.",
                recommendation="Import only the specific names needed to maintain clarity and prevent accidental name shadowing.",
                line=line,
                issue_type="Code Quality"
            )

        self.generic_visit(node)

    # ------------------------------------------------------
    # Assert detection — REMOVED from security analysis
    # Assert is a style/maintainability concern, NOT a
    # security vulnerability. It is now handled as a code
    # quality heuristic in llm_service._heuristic_analysis()
    # ------------------------------------------------------


# ----------------------------------------------------------
# Public API
# ----------------------------------------------------------

def detect_security_issues(code: str, is_test_file: bool = False, file_path: str = "") -> List[Dict]:
    """
    Analyze code and return detected security issues
    as structured dictionaries.

    Parameters
    ----------
    code : str
        Source code to analyze.
    is_test_file : bool
        If True, context-aware rules are applied:
        - subprocess usage severity is downgraded
    file_path : str
        Path to file being analyzed. Used for framework-aware
        severity adjustment (e.g., eval() in cli.py → Medium).

    Each issue contains:
        type, severity, description, recommendation, line
    """

    try:

        tree = ast.parse(code)

        analyzer = SecurityAnalyzer(
            is_test=is_test_file,
            file_path=file_path
        )

        analyzer.visit(tree)

        return analyzer.issues

    except Exception:
        return []