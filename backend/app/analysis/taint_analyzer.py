# ==========================================================
# File: taint_analyzer.py
# Location: backend/app/analysis
#
# Purpose
# ----------------------------------------------------------
# Phase 3 taint analysis. Decides, for every dangerous SINK
# call in a module (eval/exec/os.system/subprocess/pickle/...),
# whether its argument is data-flow-reachable from an external
# SOURCE, and classifies the trust boundary that reaches it.
#
# This replaces the filename-substring proxy the security
# analyzer used to guess "is this user-input driven?"
# (security_analyzer._is_framework_context) with a real,
# intra-procedural def-use trace:
#
#     q = request.args["q"]        # untrusted source
#     eval(q)                      # -> Critical (RCE)
#
#     x = sys.argv[1]              # operator/local source
#     eval(x)                      # -> Info (not remotely reachable)
#
# Propagation is INTRA-PROCEDURAL (this chunk). A value that
# flows through an unknown function call (e.g. eval(sanitize(x)))
# stops at that boundary — inter-procedural taint is Phase 4
# (call graph). This is a deliberate, documented limitation, not
# a bug: it under-reports rather than fabricating a data path.
#
# Depends on the Phase 2 SymbolTable (scope-correct name
# resolution) and ParentTracker (enclosing-scope lookup).
# Stdlib-only (ast).
# ==========================================================

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from backend.app.analysis.ast_parser import parse_module
from backend.app.analysis.symbol_table import SymbolTable

# ----------------------------------------------------------
# Trust boundaries (severity is derived from these, not filenames)
# ----------------------------------------------------------
TRUST_UNTRUSTED = "untrusted_input"   # remote / over-the-wire: web request
TRUST_OPERATOR = "operator_input"     # local: CLI argv, env, stdin
TRUST_PARAMETER = "parameter"         # function param — provenance unknown here
TRUST_INTERNAL = "internal"           # constant / derived, no external source

# Ordering for "which taint is worse" when a sink has several args.
_TIER_RANK = {
    TRUST_UNTRUSTED: 3,
    TRUST_OPERATOR: 2,
    TRUST_PARAMETER: 1,
    TRUST_INTERNAL: 0,
    None: -1,
}

_MAX_DEPTH = 12  # def-use recursion guard


# ==========================================================
# SOURCE REGISTRY
# ----------------------------------------------------------
# Multi-framework on purpose. The brief named only Flask
# `request.args`; the real set this analyzer must recognise
# spans Flask + FastAPI + Django + generic operator inputs.
# ==========================================================

_REQUEST_NAMES = {"request", "req"}

# Attribute containers that hold attacker-controlled data.
_FLASK_ATTRS = {"args", "form", "values", "json", "data",
                "cookies", "headers", "files"}
_FASTAPI_ATTRS = {"query_params", "path_params"}
_DJANGO_ATTRS = {"GET", "POST", "body", "COOKIES", "META", "FILES"}
_UNTRUSTED_ATTRS = _FLASK_ATTRS | _FASTAPI_ATTRS | _DJANGO_ATTRS

# Method calls off the request object that return untrusted data.
_REQUEST_CALL_ATTRS = {"get_json", "json", "body", "form"}
# Accessor methods off an untrusted container: request.args.get("q")
_CONTAINER_ACCESSORS = {"get", "getlist", "get_json"}


def _is_name(node: ast.AST, name: str) -> bool:
    return isinstance(node, ast.Name) and node.id == name


def _is_request_base(node: ast.AST) -> bool:
    """`request` / `req` / `self.request` / `app.request`."""
    if isinstance(node, ast.Name) and node.id in _REQUEST_NAMES:
        return True
    if isinstance(node, ast.Attribute) and node.attr == "request":
        return True
    return False


def _untrusted_container(node: ast.AST) -> bool:
    """True if `node` evaluates to remote/attacker-controlled request data."""
    if isinstance(node, ast.Attribute):
        if node.attr in _UNTRUSTED_ATTRS and _is_request_base(node.value):
            return True
    if isinstance(node, ast.Subscript):
        return _untrusted_container(node.value)          # request.args["q"]
    if isinstance(node, ast.Call):
        fn = node.func
        if isinstance(fn, ast.Attribute):
            # request.get_json() / request.json() / request.form()
            if fn.attr in _REQUEST_CALL_ATTRS and _is_request_base(fn.value):
                return True
            # request.args.get("q") / request.GET.getlist("x")
            if fn.attr in _CONTAINER_ACCESSORS and _untrusted_container(fn.value):
                return True
    return False


def _is_os_environ(node: ast.AST) -> bool:
    return (isinstance(node, ast.Attribute) and node.attr == "environ"
            and _is_name(node.value, "os"))


def _operator_source(node: ast.AST) -> Optional[str]:
    """Local, operator-controlled inputs: argv, env, stdin."""
    if isinstance(node, ast.Call):
        fn = node.func
        if isinstance(fn, ast.Name) and fn.id in {"input", "raw_input"}:
            return "stdin"
        if isinstance(fn, ast.Attribute):
            if fn.attr == "getenv" and _is_name(fn.value, "os"):
                return "env"
            if fn.attr == "get" and _is_os_environ(fn.value):
                return "env"
    if isinstance(node, ast.Attribute):
        if node.attr == "argv" and _is_name(node.value, "sys"):
            return "argv"
        if node.attr == "environ" and _is_name(node.value, "os"):
            return "env"
    return None


def _untrusted_kind(node: ast.AST) -> str:
    """Readable label for the matched untrusted source (best effort)."""
    n = node
    # peel subscripts to reach the container attribute
    for _ in range(6):
        if isinstance(n, ast.Subscript):
            n = n.value
        elif (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
              and n.func.attr in _CONTAINER_ACCESSORS):
            n = n.func.value
        else:
            break
    if isinstance(n, ast.Attribute):
        if n.attr in _FASTAPI_ATTRS:
            return f"fastapi_request.{n.attr}"
        if n.attr in _DJANGO_ATTRS:
            return f"django_request.{n.attr}"
        if n.attr in _FLASK_ATTRS:
            return f"request.{n.attr}"
    return "web_request"


def classify_source(node: ast.AST) -> Optional[Tuple[str, str]]:
    """
    Return (trust_tier, source_kind) if `node` is an external input, else None.
    Subscripts are unwrapped so request.args["q"] and sys.argv[1] classify.
    """
    if isinstance(node, ast.Subscript):
        # os.environ["X"], sys.argv[1], request.args["q"] all classify via base
        base = classify_source(node.value)
        if base:
            return base
    if _untrusted_container(node):
        return (TRUST_UNTRUSTED, _untrusted_kind(node))
    op = _operator_source(node)
    if op:
        return (TRUST_OPERATOR, op)
    return None


# ==========================================================
# SINK REGISTRY
# ----------------------------------------------------------
# Mirrors the vocabulary security_analyzer already flags so the
# two do not diverge: code execution, OS command, unsafe
# deserialization, and SQL. Each match returns the sink label,
# a category, and the argument expressions to trace.
# ==========================================================

_CODE_EXEC_BUILTINS = {"eval": "code_exec", "exec": "code_exec",
                       "compile": "code_exec"}
_SUBPROCESS_ATTRS = {"run", "call", "Popen", "check_output", "check_call"}
_DESERIALIZE = {
    ("pickle", "loads"): "pickle.loads",
    ("marshal", "loads"): "marshal.loads",
    ("yaml", "load"): "yaml.load",
    ("yaml", "loads"): "yaml.loads",
    ("yaml", "unsafe_load"): "yaml.unsafe_load",
}


def match_sink(node: ast.Call) -> Optional[Tuple[str, str, List[ast.expr]]]:
    """(sink_name, category, [tainted-arg exprs]) for a dangerous call, else None."""
    fn = node.func

    if isinstance(fn, ast.Name):
        if fn.id in _CODE_EXEC_BUILTINS and node.args:
            return (fn.id, "code_exec", [node.args[0]])
        return None

    if isinstance(fn, ast.Attribute):
        attr = fn.attr
        # os.system / os.popen
        if attr in {"system", "popen"} and _is_name(fn.value, "os") and node.args:
            return (f"os.{attr}", "command", [node.args[0]])
        # subprocess.run/call/Popen/check_output/check_call (or aliased receiver)
        if attr in _SUBPROCESS_ATTRS and node.args:
            return (f"subprocess.{attr}", "command", [node.args[0]])
        # unsafe deserialization
        if isinstance(fn.value, ast.Name):
            key = (fn.value.id, attr)
            if key in _DESERIALIZE and node.args:
                return (_DESERIALIZE[key], "deserialization", [node.args[0]])
        # DB cursor execute (SQL) — receiver name is a heuristic
        if attr in {"execute", "executemany"} and node.args:
            return (f"db.{attr}", "sql", [node.args[0]])
    return None


# ==========================================================
# Verdict
# ==========================================================

@dataclass
class TaintVerdict:
    sink_name: str
    category: str            # code_exec | command | deserialization | sql
    line: int
    tainted: bool
    trust_boundary: str      # TRUST_* constant
    source_kind: Optional[str]
    source_line: Optional[int]
    hops: int                # def-use edges between source and sink (0 = direct)
    confidence: float


@dataclass
class _TaintInfo:
    tier: str
    kind: str
    source_line: int
    hops: int


def _worse(a: Optional[_TaintInfo], b: Optional[_TaintInfo]) -> Optional[_TaintInfo]:
    if a is None:
        return b
    if b is None:
        return a
    return a if _TIER_RANK[a.tier] >= _TIER_RANK[b.tier] else b


def _confidence(info: Optional[_TaintInfo]) -> float:
    if info is None:
        return 0.60                       # sink present, no proven external taint
    if info.tier == TRUST_UNTRUSTED:
        if info.hops == 0:
            return 0.97
        return 0.92 if info.hops <= 2 else 0.85
    if info.tier == TRUST_OPERATOR:
        return 0.80
    if info.tier == TRUST_PARAMETER:
        return 0.55
    return 0.60


def _verdict(sink_name: str, category: str, line: int,
             info: Optional[_TaintInfo]) -> TaintVerdict:
    if info is None:
        return TaintVerdict(sink_name, category, line, tainted=False,
                            trust_boundary=TRUST_INTERNAL, source_kind=None,
                            source_line=None, hops=0, confidence=_confidence(None))
    return TaintVerdict(
        sink_name, category, line, tainted=True, trust_boundary=info.tier,
        source_kind=info.kind, source_line=info.source_line,
        hops=info.hops, confidence=_confidence(info),
    )


# ==========================================================
# Propagation (intra-procedural def-use via SymbolTable)
# ==========================================================

# String/collection transforms taint flows THROUGH (value-preserving).
_PASSTHROUGH_FUNCS = {"str", "bytes", "bytearray", "list", "tuple", "set",
                      "dict", "repr", "format"}
_PASSTHROUGH_METHODS = {"format", "format_map", "join", "strip", "lstrip",
                        "rstrip", "lower", "upper", "replace", "encode",
                        "decode", "title", "capitalize", "expandtabs",
                        "zfill", "center", "ljust", "rjust"}


def _enclosing_scope(node: ast.AST, st: SymbolTable) -> int:
    """Innermost scope id that owns `node`, via ParentTracker back-links."""
    cur: Optional[ast.AST] = node
    while cur is not None:
        sid = st.scope_of_node.get(cur)
        if sid is not None:
            return sid
        cur = getattr(cur, "parent", None)
    return st.scope_of_node.get(st.tree, 0)


def _first_taint(nodes, scope_id, at_line, st, depth, seen):
    best = None
    for n in nodes:
        best = _worse(best, _resolve_taint(n, scope_id, at_line, st, depth, seen))
        if best is not None and best.tier == TRUST_UNTRUSTED:
            break  # cannot get worse
    return best


def _resolve_taint(expr, scope_id: int, at_line: int, st: SymbolTable,
                   depth: int, seen: frozenset) -> Optional[_TaintInfo]:
    if expr is None or depth > _MAX_DEPTH:
        return None
    nid = id(expr)
    if nid in seen:
        return None
    seen = seen | {nid}

    # 1) Is this expression itself an external source?
    src = classify_source(expr)
    if src:
        tier, kind = src
        return _TaintInfo(tier, kind, getattr(expr, "lineno", at_line), depth)

    # 2) Value-preserving combinators
    if isinstance(expr, ast.BinOp):                     # a + b, "x %" % v
        return _first_taint([expr.left, expr.right], scope_id, at_line, st, depth + 1, seen)
    if isinstance(expr, ast.BoolOp):
        return _first_taint(expr.values, scope_id, at_line, st, depth + 1, seen)
    if isinstance(expr, ast.IfExp):
        return _first_taint([expr.body, expr.orelse], scope_id, at_line, st, depth + 1, seen)
    if isinstance(expr, ast.JoinedStr):                 # f-string
        vals = [v.value for v in expr.values if isinstance(v, ast.FormattedValue)]
        return _first_taint(vals, scope_id, at_line, st, depth + 1, seen)
    if isinstance(expr, (ast.List, ast.Tuple, ast.Set)):
        return _first_taint(list(expr.elts), scope_id, at_line, st, depth + 1, seen)
    if isinstance(expr, ast.Starred):
        return _resolve_taint(expr.value, scope_id, at_line, st, depth + 1, seen)
    if isinstance(expr, ast.Subscript):                 # tainted_container[k]
        return _resolve_taint(expr.value, scope_id, at_line, st, depth + 1, seen)
    if isinstance(expr, ast.Attribute):                 # tainted.attr
        return _resolve_taint(expr.value, scope_id, at_line, st, depth + 1, seen)

    # 3) Passthrough calls (str()/bytes()/.format()/.join()/...); other calls are
    #    an intra-procedural boundary and stop propagation (documented limitation).
    if isinstance(expr, ast.Call):
        fn = expr.func
        if isinstance(fn, ast.Name) and fn.id in _PASSTHROUGH_FUNCS:
            return _first_taint(list(expr.args), scope_id, at_line, st, depth + 1, seen)
        if isinstance(fn, ast.Attribute) and fn.attr in _PASSTHROUGH_METHODS:
            cand = [fn.value] + list(expr.args)          # receiver + args
            return _first_taint(cand, scope_id, at_line, st, depth + 1, seen)
        return None

    # 4) Name — resolve its binding through the scope chain and follow it.
    if isinstance(expr, ast.Name):
        sym = st.lookup(expr.id, scope_id, at_line=at_line)
        if sym is None:
            return None
        if sym.source_type == "Parameter":
            return _TaintInfo(TRUST_PARAMETER, f"parameter:{expr.id}", sym.line, depth)
        if sym.source_type == "Import":
            return None
        # Follow the def-use edge to the expression that produced the value,
        # continuing the trace from the binding's own scope/line.
        return _resolve_taint(sym.source_node, sym.scope_id, sym.line, st,
                              depth + 1, seen)

    return None


# ==========================================================
# Public API
# ==========================================================

def build_taint_map(tree: ast.AST, st: SymbolTable) -> Dict[ast.Call, TaintVerdict]:
    """
    Map every dangerous sink Call node in `tree` to its TaintVerdict.
    Keyed by the Call node itself so the security analyzer can look up a
    verdict by node identity (no fragile line matching). Never raises.
    """
    out: Dict[ast.Call, TaintVerdict] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        sink = match_sink(node)
        if sink is None:
            continue
        sink_name, category, arg_nodes = sink
        scope_id = _enclosing_scope(node, st)
        line = getattr(node, "lineno", 0)
        best = None
        for arg in arg_nodes:
            best = _worse(best, _resolve_taint(arg, scope_id, line, st, 0, frozenset()))
        out[node] = _verdict(sink_name, category, line, best)
    return out


def analyze_taint(code: str) -> List[TaintVerdict]:
    """
    Standalone entry point: parse `code`, build the symbol table, and return
    a TaintVerdict for every dangerous sink. Returns [] on syntax error.
    """
    tree = parse_module(code)      # attaches .parent via ParentTracker
    if tree is None:
        return []
    st = SymbolTable(tree).build()
    verdicts = build_taint_map(tree, st)
    return sorted(verdicts.values(), key=lambda v: (v.line, v.sink_name))
