# ==========================================================
# File: security_analyzer.py
# Purpose: Detect common security vulnerabilities in code
# ==========================================================

import ast
import re
from typing import List, Dict

from backend.app.analysis.ast_parser import parse_module
from backend.app.analysis.symbol_table import SymbolTable
from backend.app.analysis.taint_analyzer import (
    build_taint_map, TRUST_UNTRUSTED, TRUST_OPERATOR, TRUST_PARAMETER,
)
from backend.app.services.snippet import extract_snippet

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

# PHASE G / S2: SQL statement shape.
#
# Both SQL detectors used to substring-match the verbs select|insert|update|
# delete, so "Failed to delete {name}" was reported as SQL injection at High.
# A verb is not a query. Two conditions now have to hold.
#
# First, the string must BEGIN with a SQL verb. Matching `select ... from`
# anywhere still swallows ordinary prose -- "Please select an option from the
# menu" -- whereas a real interpolated query is written starting at the verb,
# which is what every true positive in the corpus does.
_SQL_LEADING_VERB = re.compile(
    r"^\s*\(?\s*(?:"
    r"with\b[\s\S]*?\bselect\b"
    r"|select\b"
    r"|insert\s+into\b"
    r"|replace\s+into\b"
    r"|update\b"
    r"|delete\s+from\b"
    r"|truncate\s+table\b"
    r"|drop\s+(?:table|index|view|database)\b"
    r"|alter\s+table\b"
    r"|create\s+(?:table|index|view|database)\b"
    r")",
    re.IGNORECASE,
)

# Second, a clause keyword must appear. This is what separates the imperative
# sentence "Select a file to insert ..." from "SELECT id FROM ...".
_SQL_CLAUSE = re.compile(r"\b(?:from|set|values|where|join|into)\b", re.IGNORECASE)


def _looks_like_sql(text: str) -> bool:
    """True when `text` has the shape of a SQL statement, not merely a SQL word."""
    return bool(_SQL_LEADING_VERB.match(text)) and bool(_SQL_CLAUSE.search(text))


# The one subprocess verdict that clears a call instead of flagging it. Shared
# between _classify_subprocess_call (which emits it) and visit_Call (which
# suppresses it as benign), so the two cannot drift apart silently.
SAFE_SUBPROCESS_INVOCATION = 'list argv with shell=False naming a non-shell program — safe invocation pattern'

# PHASE G / S3: argv[0] decides whether a list invocation is safe.
#
# Under shell=False the list is handed to execve as-is, so no element after
# argv[0] can begin a new command — it can only ever be an argument to the
# program argv[0] names. Element constancy is therefore the wrong test:
# `subprocess.run(["git", *args])` is safe and was being reported, while
# `["sh", "-c", user]` is a live injection and must not be cleared.
#
# The exception is a program whose job is to run another command. For those the
# rest of argv IS a command line again and the argument is back in play.
_SHELL_PROGRAMS = frozenset({
    "sh", "bash", "zsh", "dash", "ksh", "csh", "tcsh", "fish", "ash", "busybox",
    "cmd", "cmd.exe", "command.com", "powershell", "powershell.exe", "pwsh",
    "pwsh.exe", "env", "xargs", "nohup", "timeout", "sudo", "ssh",
})

# The flags that turn an otherwise ordinary program into a command interpreter.
_SHELL_COMMAND_FLAGS = frozenset({"-c", "/c", "--command", "-command", "-encodedcommand"})


def _argv_program_is_safe(argv: ast.List) -> bool:
    """True when a list argv names a fixed, non-shell program.

    Requires argv[0] to be a string literal: if the program itself is a
    variable the attacker chooses what runs, which is the worst case, not a
    safe one. Non-constant elements AFTER argv[0] are fine and are exactly the
    case this exists to clear.
    """
    if not argv.elts:
        return False

    # Phase C's rule, kept rather than replaced. A fully literal argv has no
    # input to inject, whatever argv[0] names -- RLPROJECT queries a memory
    # counter with a hardcoded PowerShell command line, which the argv[0] rule
    # alone rejected. Judging it dangerous requires believing a constant can
    # vary.
    if all(isinstance(element, ast.Constant) for element in argv.elts):
        return True

    first = argv.elts[0]
    if not (isinstance(first, ast.Constant) and isinstance(first.value, str)):
        return False

    program = first.value.replace("\\", "/").rsplit("/", 1)[-1].lower()
    if program in _SHELL_PROGRAMS:
        return False

    return not any(
        isinstance(element, ast.Constant)
        and isinstance(element.value, str)
        and element.value.lower() in _SHELL_COMMAND_FLAGS
        for element in argv.elts
    )


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
        # Findings the analyzer positively cleared as benign. Retained so the
        # reasoning is inspectable, but deliberately not part of `issues`.
        self.suppressed: List[Dict] = []
        self.is_test = is_test
        self.file_path = file_path.replace("\\", "/").lower()

        # PHASE 3: per-sink taint verdicts keyed by Call node (may be empty).
        # Populated by detect_security_issues() from the taint analyzer so
        # visit_Call can look up a verdict by node identity.
        self.taint_map = taint_map or {}

        # PHASE 1: source lines and parent map
        # split("\n"), not splitlines(): splitlines() also breaks on form
        # feed, vertical tab, and other exotic separators the AST's tokenizer
        # does not treat as a line ending, which would drift every lineno
        # above such a character out of alignment with this array.
        self._source_lines: list[str] = source.split("\n") if source else []
        self._parent_map: dict = {}

        # PHASE G / S1: import bindings, so a call target can be resolved to
        # the module it actually belongs to. Populated by bind_imports() before
        # the walk. Without this the detector matches the bare attribute name,
        # and `subprocess.run` is indistinguishable from Flask's `app.run` —
        # which on real repositories was every command-injection finding.
        self._module_aliases: dict[str, str] = {}   # local name -> module
        self._name_bindings: dict[str, str] = {}    # local name -> "module.attr"

        # PHASE G / S3: names bound exactly once to a list literal, so that
        # `cmd = ["git", "status"]` followed by `subprocess.run(cmd)` can be
        # judged on its argv instead of being written off as dynamic.
        self._list_bindings: dict[str, ast.List] = {}

        # Framework-aware file patterns where eval/exec/compile are expected
        # and controlled (not user-input driven).
        #
        # NARROWED in Phase C. This used to also match "app.py", "__init__.py",
        # "factory", "loader", "runner" and "commands" — among the most common
        # names in any Python project — so an eval() in a plain app.py was
        # reframed as an intentional pattern. That was survivable only while
        # such findings were still emitted at low severity; the moment benign
        # patterns stopped being reported it became a silent false negative,
        # and the benchmark caught it at once (dangerous_function fixture
        # recall 1.00 -> 0.00, its true positives living in app.py).
        #
        # What is left is the narrow, genuinely documented case: a CLI shell
        # and a config loader executing the developer's OWN file. Widening this
        # list trades recall for nothing — taint already handles real input.
        self._is_framework_context = any(
            pat in self.file_path for pat in ("cli.py", "config.py")
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
    # Call-target resolution (PHASE G / S1)
    # ------------------------------------------------------

    def bind_imports(self, tree: ast.AST) -> None:
        """Record this module's import bindings for call-target resolution.

        Runs over the whole tree BEFORE the walk on purpose. Visit order does
        not guarantee an import is seen before the call that uses it — a
        function body is visited where it is defined, and a late or
        conditional import is common — and a binding missed that way turns a
        true positive silent, which is the worse direction to fail in.
        """
        for node in ast.walk(tree):

            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.asname:
                        self._module_aliases[alias.asname] = alias.name
                    else:
                        # `import os.path` binds the name `os`, not `os.path`.
                        root = alias.name.split(".")[0]
                        self._module_aliases[root] = root

            elif isinstance(node, ast.ImportFrom) and node.module:
                for alias in node.names:
                    if alias.name != "*":
                        local = alias.asname or alias.name
                        self._name_bindings[local] = f"{node.module}.{alias.name}"

    def bind_list_literals(self, tree: ast.AST) -> None:
        """Record names bound exactly ONCE to a list literal (PHASE G / S3).

        Exactly once is the whole point. With two bindings, which list reaches
        the call is not decidable from a single pass, and the safe answer is to
        go on treating the argument as dynamic rather than to clear it.

        Deliberately module-wide rather than scope-aware: two functions that
        both use the name `cmd` simply stop resolving, which errs towards
        reporting. Scope-correct resolution is the SymbolTable's job and is not
        worth pulling in for this.
        """
        counts: dict[str, int] = {}
        candidates: dict[str, ast.List] = {}

        for node in ast.walk(tree):

            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                counts[node.id] = counts.get(node.id, 0) + 1

            if isinstance(node, ast.Assign) and isinstance(node.value, ast.List):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        candidates[target.id] = node.value

        self._list_bindings = {
            name: value for name, value in candidates.items() if counts.get(name) == 1
        }

    def _resolve_argv(self, arg0: ast.AST) -> ast.List:
        """The list literal behind a subprocess first argument, if there is one."""
        if isinstance(arg0, ast.List):
            return arg0
        if isinstance(arg0, ast.Name):
            return self._list_bindings.get(arg0.id)
        return None

    def _resolve_module(self, value: ast.AST) -> str:
        """Best-effort module name for the receiver of an attribute call.

        `subprocess.run` -> "subprocess"; `sp.run` under `import subprocess as
        sp` -> "subprocess"; `app.run` -> "app". An unimported plain name
        resolves to itself rather than to nothing, so a snippet that omits its
        imports is still analysed correctly.

        Anything that is not a plain name — `self.client.run`, `get().run` —
        returns "", which reads correctly as "not the module we are after".
        """
        if isinstance(value, ast.Name):
            return self._module_aliases.get(value.id, value.id)
        return ""

    def _report_os_system(self, node: ast.Call, line: int) -> None:
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

    def _report_subprocess_call(self, node: ast.Call, line: int) -> None:
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
            # Checked AFTER taint on purpose: _apply_taint replaces the
            # description for untrusted-input sinks, so a call that
            # still carries the marker here is one taint also cleared.
            benign=SAFE_SUBPROCESS_INVOCATION in message,
        )

    # ------------------------------------------------------
    # Helper to add structured issue
    # ------------------------------------------------------

    def _add_issue(self, severity: str, description: str, recommendation: str, line: int = 0,
                   issue_type: str = "Vulnerability", trust_boundary: str = "n/a",
                   confidence_override: float = None, benign: bool = False):

        # ----------------------------------------------------
        # Benign-pattern suppression (Phase C / A2)
        # ----------------------------------------------------
        # A findings list is a request for the reader's attention. An entry the
        # analyzer has already cleared — "computationally secure for message
        # signing", "[Intentional Pattern] ... from a trusted path" — spends
        # that attention and then returns nothing, so it is a false positive
        # regardless of how low its severity is. Cleared findings are kept on
        # `self.suppressed` for debugging rather than deleted.
        #
        # SAFETY: this cannot mask a tainted sink. The "[Intentional Pattern]"
        # framing comes from a filename heuristic, but _apply_taint REPLACES
        # the description wholesale when the sink is reachable from untrusted
        # input (TRUST_UNTRUSTED branch), so the marker is already gone by the
        # time a genuinely dangerous call reaches here. Taint outranks the
        # filename proxy, which is the ordering test_benign_pattern_suppression
        # exists to pin.
        if benign or "[Intentional Pattern]" in description:
            self.suppressed.append({
                "type": issue_type,
                "severity": severity,
                "description": description,
                "line": line,
                "reason": "analyzer determined this pattern is benign",
            })
            return

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
            # Real evidence, not a restatement of the line number. Empty when
            # the analyzer was constructed without source (see snippet.py).
            "snippet": extract_snippet(self._source_lines, line),
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

    # The one subprocess classification that asserts safety rather than risk.
    # Named because two places must agree on it: the classifier that produces it
    # and the call site that suppresses it as benign (Phase C / A2 mechanism).
    # Taint outranks it — _apply_taint replaces the description wholesale for
    # untrusted-input sinks, so the marker is gone before suppression is decided.

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

        argv = self._resolve_argv(arg0)

        if argv is not None:
            # "list form" is NOT the same as safe. ['sh', '-c', user] is a list,
            # carries no shell=True, and is still a live command injection;
            # calling it safe was worse than over-reporting, because the reader
            # was handed a vector with the word "safe" attached.
            #
            # PHASE G / S3: but element constancy was the wrong test for the
            # other direction. Under shell=False only argv[0] chooses the
            # program, so ['git', *args] is inert and was being reported. The
            # gate is argv[0]; anything it does not clear falls through to the
            # dynamic-argument branch below, where it always belonged.
            if _argv_program_is_safe(argv):
                if shell_true:
                    return 'Medium', 'list argv with shell=True — shell flag is redundant and risky'
                return 'Low', SAFE_SUBPROCESS_INVOCATION

        elif isinstance(arg0, ast.Constant) and isinstance(arg0.value, str):
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

            # PHASE G / S1: `from subprocess import run` / `from os import
            # system` produce a bare Name call, not an Attribute. Tightening
            # the attribute branch to a resolved receiver would have made
            # these silent, so resolve the from-import binding here.
            bound = self._name_bindings.get(name, "")

            if bound == "os.system":
                self._report_os_system(node, line)
            elif bound in {"subprocess.Popen", "subprocess.call", "subprocess.run"}:
                self._report_subprocess_call(node, line)
                _handled_as_subprocess = True

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

            # PHASE G / S1: resolve the receiver before matching the name.
            # Matching `attr` alone made `app.run(debug=True)` — the most
            # common single line in a Flask application — a Command Injection
            # finding, along with every `self.run()`, `scheduler.run()` and
            # `manager.system()` in the corpus.
            receiver = self._resolve_module(node.func.value)

            # os.system
            if attr == "system" and receiver == "os":
                self._report_os_system(node, line)

            # subprocess commands
            if attr in {"Popen", "call", "run"} and receiver == "subprocess":
                self._report_subprocess_call(node, line)
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

                    # PHASE G / S2: shape, not a bare verb -- and a dynamic
                    # right-hand side, since concatenating two literals
                    # produces a constant that cannot be injected into.
                    dynamic = not isinstance(node.right, ast.Constant)

                    if dynamic and _looks_like_sql(node.left.value):
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

        # PHASE G / S2: an f-string with nothing interpolated is a constant,
        # and a constant carries no injection. Previously every literal chunk
        # was tested on its own, which both produced duplicate findings and
        # missed a query whose keywords straddle an interpolation. Joining the
        # chunks first fixes both: `f"SELECT {cols} FROM {tbl}"` reads as
        # "SELECT   FROM  ". The separator is a space so that `f"SELECT{x}FROM"`
        # does not glue into a single token.
        if any(isinstance(value, ast.FormattedValue) for value in node.values):

            literal = " ".join(
                str(value.value)
                for value in node.values
                if isinstance(value, ast.Constant)
            )

            if _looks_like_sql(literal):
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
                    issue_type="Weak Cryptography",
                    # SHA-1 under HMAC is a correct construction, not a weak
                    # hash. Reporting it means the findings list contains an
                    # entry whose own text says "computationally secure".
                    benign=(context == 'hmac_digest'),
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

def detect_security_issues(code: str, is_test_file: bool = False, file_path: str = "",
                           include_benign: bool = False) -> List[Dict]:
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
    include_benign : bool
        If True, also return the findings the analyzer positively CLEARED
        (SHA-1 under HMAC, an intentional framework pattern), each tagged
        `benign=True`. Off by default: a security findings list that contains
        entries whose own text says "this is secure" spends the reader's
        attention and returns nothing. Turn it on to inspect the reasoning.

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

        # PHASE G: bind module-level facts before the walk — imports so call
        # targets resolve (S1), list literals so an argv held in a variable can
        # be judged on its contents (S3).
        analyzer.bind_imports(tree)
        analyzer.bind_list_literals(tree)

        analyzer.visit(tree)

        if include_benign:
            return analyzer.issues + [
                dict(item, benign=True) for item in analyzer.suppressed
            ]
        return analyzer.issues

    except Exception:
        return []