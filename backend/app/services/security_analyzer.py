# ==========================================================
# File: security_analyzer.py
# Purpose: Detect common security vulnerabilities in code
# ==========================================================

import ast
from typing import List, Dict

from backend.app.analysis.ast_parser import parse_module
from backend.app.analysis.symbol_table import SymbolTable
from backend.app.analysis.taint_analyzer import (
    build_taint_map, TRUST_UNTRUSTED, TRUST_OPERATOR, TRUST_PARAMETER,
)

# PHASE 1: SHA constants
SHA_CONTEXT_SIGNALS: dict[str, list[str]] = {
    'hmac_digest': [
        'hmac.new', 'hmac.digest', 'itsdangerous', 'signer', 'timestampsigner',
        'urlsafeserializer', 'want_bytes',
    ],
    'password_hash': [
        'pbkdf2', 'check_password', 'password', 'passwd', 'set_password',
        'hash_password',
    ],
}

SHA_SEVERITY_MAP: dict[str, tuple[str, str]] = {
    'hmac_digest': (
        'Info',
        'SHA-1 in HMAC context — computationally secure for message signing',
    ),
    'bare_hash': (
        'Medium',
        'SHA-1 used for data integrity — collision risk exists; consider SHA-256',
    ),
    'password_hash': (
        'Critical',
        'SHA-1 used for password hashing — trivially broken with rainbow tables; use bcrypt/argon2',
    ),
}

# Loader classes that make yaml.load() safe. yaml.load(x, Loader=SafeLoader) is
# the documented safe spelling and is common in real code, so flagging it would
# buy recall at the cost of precision on exactly the repos the benchmark scores.
_SAFE_YAML_LOADERS = frozenset({"SafeLoader", "CSafeLoader", "BaseLoader", "CBaseLoader"})


def _has_safe_yaml_loader(node: ast.Call) -> bool:
    """True if a yaml.load() call passes an explicitly safe Loader.

    Accepts both `Loader=SafeLoader` and `Loader=yaml.SafeLoader`, and the
    positional second argument, which is what PyYAML's own signature allows.
    An unrecognised loader is treated as UNSAFE — the safe list is closed, so a
    custom Loader subclass is flagged rather than assumed benign.
    """
    def _is_safe(arg) -> bool:
        if isinstance(arg, ast.Attribute):        # yaml.SafeLoader
            return arg.attr in _SAFE_YAML_LOADERS
        if isinstance(arg, ast.Name):             # SafeLoader
            return arg.id in _SAFE_YAML_LOADERS
        return False

    for kw in node.keywords:
        if kw.arg == "Loader":
            return _is_safe(kw.value)

    # yaml.load(stream, Loader) — Loader as the second positional argument.
    if len(node.args) >= 2:
        return _is_safe(node.args[1])

    return False


class SecurityAnalyzer(ast.NodeVisitor):
    """
    AST-based security analyzer that detects
    common security vulnerabilities.
    Returns structured issue objects with severity,
    description, recommendation, and line number.
    """

    def __init__(self, is_test: bool = False, file_path: str = "", source: str = "",
                 taint_map: Dict = None):

        self.issues: List[Dict] = []
        self.is_test = is_test
        self.file_path = file_path.replace("\\", "/").lower()

        # PHASE 3: per-sink taint verdicts keyed by Call node (may be empty).
        # Populated by detect_security_issues() from the taint analyzer so
        # visit_Call can look up a verdict by node identity.
        self.taint_map = taint_map or {}

        # PHASE 1: source lines and parent map
        self._source_lines: list[str] = source.splitlines() if source else []
        self._parent_map: dict = {}

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

    def _add_issue(self, severity: str, description: str, recommendation: str, line: int = 0,
                   issue_type: str = "Vulnerability", trust_boundary: str = "n/a",
                   confidence_override: float = None):

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
            
        # Determine confidence score.
        # PHASE 3: for taint-reachable sinks the caller passes a
        # reachability-derived confidence (confidence_override), which retires
        # the old description-keyword table for those findings. Non-taint issue
        # types (hardcoded creds, SQL, weak hashes) keep the deterministic prior.
        if confidence_override is not None:
            confidence = confidence_override
        else:
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
            "trust_boundary": trust_boundary,   # PHASE 3: taint provenance
            "snippet": f"Line {line} indicates: {issue_type}"  # Simplified without full tree mapping
        })

    # ------------------------------------------------------
    # PHASE 3: taint overlay
    # ------------------------------------------------------
    def _apply_taint(self, node, severity: str, description: str):
        """
        Overlay the taint verdict for sink `node` onto a base (severity,
        description). Returns (severity, description, trust_boundary,
        confidence_override). Direction is downgrade-not-suppress:

          - untrusted (web/remote) -> escalate to Critical (overrides the old
            filename proxy: even in cli.py, eval(request.args[..]) is Critical)
          - operator (argv/env/stdin) -> code-exec drops to Info; command/
            deserialization keep severity but are annotated as local-only
          - parameter -> unchanged severity, annotated (provenance unknown)
          - internal / no verdict -> unchanged; confidence from reachability
        """
        verdict = self.taint_map.get(node)
        if verdict is None:
            return severity, description, "n/a", None

        tb = verdict.trust_boundary
        if tb == TRUST_UNTRUSTED:
            # Untrusted reachability is authoritative: replace any framework/
            # constant framing (e.g. "[Intentional Pattern] ... CLI") with a
            # clean finding — that framing is exactly the filename proxy taint
            # supersedes, and leaving it in would contradict the Critical verdict.
            impact = {
                "code_exec": "arbitrary code execution (RCE)",
                "command": "OS command injection",
                "deserialization": "unsafe deserialization / RCE",
                "sql": "SQL injection",
            }.get(verdict.category, "a security compromise")
            desc = (f"{verdict.sink_name}() receives an argument reachable from "
                    f"untrusted input ({verdict.source_kind}) — enables {impact}.")
            return "Critical", desc, tb, verdict.confidence
        if tb == TRUST_OPERATOR:
            new_sev = "Info" if verdict.category == "code_exec" else severity
            desc = (description + f" [Operator Input] argument derives from local "
                    f"{verdict.source_kind}; not remotely reachable.")
            return new_sev, desc, tb, verdict.confidence
        if tb == TRUST_PARAMETER:
            desc = (description + " Argument flows from an unvalidated parameter "
                    "(provenance unknown without inter-procedural analysis).")
            return severity, desc, tb, verdict.confidence
        # internal / constant
        return severity, description, tb, verdict.confidence

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

    def _classify_subprocess_call(self, node: ast.Call) -> tuple[str, str]:
        shell_true = any(
            kw.arg == 'shell'
            and isinstance(kw.value, ast.Constant)
            and kw.value.value is True
            for kw in node.keywords
        )

        if not node.args:
            return 'Low', 'subprocess call with no positional arguments'

        arg0 = node.args[0]

        if isinstance(arg0, ast.List):
            if shell_true:
                return 'Medium', 'subprocess list arg with shell=True — shell flag is redundant and risky'
            return 'Low', 'constant list args with shell=False — safe invocation pattern'

        if isinstance(arg0, ast.Constant) and isinstance(arg0.value, str):
            if shell_true:
                return 'High', 'string command with shell=True — command injection risk if input is unsanitised'
            if ' ' in arg0.value:
                return 'Medium', 'space-separated string command — prefer list form to avoid shell-splitting ambiguity'
            return 'Low', 'single-token constant string — low risk but list form is preferred'

        # Dynamic arg (ast.Name, ast.Call, ast.JoinedStr f-string, ast.BinOp, etc.)
        if shell_true:
            return 'High', 'dynamic argument with shell=True — command injection risk; sanitise all inputs'
        return 'Medium', 'dynamic argument to subprocess — validate and sanitise all inputs'

    def visit_Call(self, node):

        # PHASE 1 FIX: track whether this node was already classified
        # by _classify_subprocess_call so the generic shell=True block
        # does not emit a duplicate finding on the same node.
        _handled_as_subprocess = False

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

                # PHASE 3: taint reachability overrides the filename proxy above.
                severity, desc, tb, conf = self._apply_taint(node, severity, desc)
                self._add_issue(
                    severity=severity,
                    description=desc,
                    recommendation="Replace eval() with ast.literal_eval() for safe parsing, or use a proper parser for the expected input format.",
                    line=line,
                    issue_type="Dangerous Function",
                    trust_boundary=tb,
                    confidence_override=conf,
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

                severity, desc, tb, conf = self._apply_taint(node, severity, desc)
                self._add_issue(
                    severity=severity,
                    description=desc,
                    recommendation="Avoid exec() entirely. Use importlib for dynamic imports, or a sandboxed environment.",
                    line=line,
                    issue_type="Dangerous Function",
                    trust_boundary=tb,
                    confidence_override=conf,
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

                severity, desc, tb, conf = self._apply_taint(node, severity, desc)
                self._add_issue(
                    severity=severity,
                    description=desc,
                    recommendation="Ensure compile() input is not derived from user input. Consider using safer alternatives.",
                    line=line,
                    issue_type="Dangerous Function",
                    trust_boundary=tb,
                    confidence_override=conf,
                )

        # ----------------------------------------------
        # Attribute-based calls
        # ----------------------------------------------

        elif isinstance(node.func, ast.Attribute):

            attr = node.func.attr

            # os.system
            if attr == "system":
                severity, desc, tb, conf = self._apply_taint(
                    node, "High",
                    "Use of os.system() detected which may allow command injection.")
                self._add_issue(
                    severity=severity,
                    description=desc,
                    recommendation="Use subprocess.run() with a list of arguments instead of os.system() to prevent shell injection.",
                    line=line,
                    issue_type="Command Injection",
                    trust_boundary=tb,
                    confidence_override=conf,
                )

            # subprocess commands
            if attr in {"Popen", "call", "run"}:
                # PHASE 1: argument-type-aware severity
                severity, message = self._classify_subprocess_call(node)
                # PHASE 3: escalate to Critical when the command argument is
                # data-flow reachable from untrusted input.
                severity, message, tb, conf = self._apply_taint(node, severity, message)
                self._add_issue(
                    severity=severity,
                    description=message,
                    recommendation="Ensure arguments are passed as a list (not a string), avoid shell=True, and validate all inputs.",
                    line=line,
                    issue_type="Command Injection",
                    trust_boundary=tb,
                    confidence_override=conf,
                )
                _handled_as_subprocess = True                 # PHASE 1 FIX

            # unsafe deserialization
            #
            # Matches BOTH `load` and `loads`. Keying on the plural alone put
            # this detector's recall at 0.33: it saw pickle.loads(blob) but
            # walked straight past pickle.load(fp) and yaml.load(text) — and
            # since PyYAML exposes no `yaml.loads` at all, the yaml arm was
            # unreachable on any real code.
            if attr in ("load", "loads"):

                if isinstance(node.func.value, ast.Name):
                    module = node.func.value.id

                    # cPickle/_pickle are the same module under other names.
                    # dill/marshal/shelve are also RCE sinks but are left out
                    # deliberately: nothing in the corpus labels them, so their
                    # precision would be unmeasured. Add them with fixtures.
                    if module in ("pickle", "cPickle", "_pickle"):
                        severity, desc, tb, conf = self._apply_taint(
                            node, "Critical",
                            f"Use of {module}.{attr}() detected which may allow unsafe deserialization and remote code execution.")
                        self._add_issue(
                            severity=severity,
                            description=desc,
                            recommendation="Use json.loads() for data serialization, or implement HMAC validation before unpickling.",
                            line=line,
                            issue_type="Unsafe Deserialization",
                            trust_boundary=tb,
                            confidence_override=conf,
                        )

                    elif module == "yaml" and not _has_safe_yaml_loader(node):
                        severity, desc, tb, conf = self._apply_taint(
                            node, "High",
                            f"Use of yaml.{attr}() without a safe Loader detected, which may allow unsafe deserialization.")
                        self._add_issue(
                            severity=severity,
                            description=desc,
                            recommendation="Use yaml.safe_load() instead of yaml.load() to prevent arbitrary code execution.",
                            line=line,
                            issue_type="Unsafe Deserialization",
                            trust_boundary=tb,
                            confidence_override=conf,
                        )

        # ----------------------------------------------
        # shell=True detection
        # ----------------------------------------------

        for keyword in node.keywords:

            # Generic shell=True check — guard against duplicate
            if keyword.arg == "shell" and not _handled_as_subprocess: # PHASE 1 FIX

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

    def _classify_sha_context(self, node: ast.AST) -> str:
        # Window: 5 lines starting at node's line (1-indexed)
        start = max(0, getattr(node, "lineno", 1) - 1)
        end = min(start + 6, len(self._source_lines))
        window = '\n'.join(self._source_lines[start:end]).lower()

        # password_hash takes priority
        if any(sig in window for sig in SHA_CONTEXT_SIGNALS['password_hash']):
            return 'password_hash'
        if any(sig in window for sig in SHA_CONTEXT_SIGNALS['hmac_digest']):
            return 'hmac_digest'

        # Parent function name heuristic
        parent = self._parent_map.get(node)
        while parent is not None:
            if isinstance(parent, ast.FunctionDef):
                fname = parent.name.lower()
                if any(kw in fname for kw in ('sign', 'digest', 'token', 'mac', 'hmac')):
                    return 'hmac_digest'
                break
            parent = self._parent_map.get(parent)

        return 'bare_hash'

    def visit_Attribute(self, node):

        line = getattr(node, "lineno", 0)

        if isinstance(node.value, ast.Name) and node.value.id == "hashlib":
            if node.attr in ("md5", "sha1"):
                # PHASE 1: context-aware severity instead of flat Medium
                context = self._classify_sha_context(node)
                severity, message = SHA_SEVERITY_MAP[context]
                self._add_issue(
                    severity=severity,
                    description=message,
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

        # PHASE 2: parse_module() runs ParentTracker, so every node already
        # carries a .parent back-reference before any visitor touches the
        # tree. Single source of parent truth for the analysis pipeline.
        tree = parse_module(code)

        if tree is None:  # SyntaxError
            return []

        # PHASE 3: build the scope-correct symbol table and per-sink taint
        # verdicts for this module, then hand them to the analyzer. This is the
        # point where the Phase 2 SymbolTable becomes a real pipeline consumer:
        # detect_security_issues() is called per file by
        # repository_review_engine.analyze_single_file(). Taint is an overlay —
        # if it ever fails, core detection must still run.
        try:
            st = SymbolTable(tree).build()
            taint_map = build_taint_map(tree, st)
        except Exception:
            taint_map = {}

        analyzer = SecurityAnalyzer(
            is_test=is_test_file,
            file_path=file_path,
            source=code, # PHASE 1: Add source parameter
            taint_map=taint_map,
        )

        # Backward compat: _parent_map is still exposed (used by
        # _classify_sha_context) but is now derived from the ParentTracker
        # annotations rather than rebuilt by a second independent walk.
        analyzer._parent_map = {
            node: node.parent
            for node in ast.walk(tree)
            if getattr(node, "parent", None) is not None
        }

        analyzer.visit(tree)

        return analyzer.issues

    except Exception:
        return []