# ==========================================================
# File: js_structure.py
# Location: backend/app/analysis
#
# Purpose (Phase 6 / Chunk 5)
# ----------------------------------------------------------
# Tree-sitter structural analysis for JavaScript / TypeScript.
#
# Until now only Python files received AST-based structural rules. JS/TS/JSX/TSX
# files were walked and language-detected, then reported with a STUB cyclomatic
# complexity of 1.0 / O(1) and no function inventory — so a 400-line React
# component with deeply nested logic looked exactly as simple as an empty file,
# never triggered a maintainability warning, never showed up in "most complex
# files", and never moved the simplicity score.
#
# This module closes that gap. It parses JS/JSX/TS/TSX with tree-sitter and emits
# the SAME per-function complexity shape that
# complexity_analyzer.ComplexityAnalyzer produces for Python, so JS/TS files flow
# through the identical downstream machinery in repo_analyzer /
# repository_review_engine with no special-casing there.
#
# Design decisions
# ----------------
# * OPTIONAL dependency. If tree-sitter (or a grammar) is missing/incompatible at
#   runtime, analyze() degrades to the previous behaviour (empty metrics) after a
#   single LOUD warning per process. The pipeline must never crash because an
#   optional analysis dependency is absent — same never-silent-but-never-fatal
#   contract as the parallel pool fallback in repo_analyzer.
# * PER-FUNCTION metrics. Complexity is measured per function; the walk does NOT
#   descend into a nested function/method/arrow, so each function owns only its
#   own decision points. (This is a deliberate, documented divergence from the
#   Python analyzer, which folds a nested def's complexity into its parent.)
# * ROLE-AWARE verdicts reuse ComplexityAnalyzer, so risk_level / hotspot for a JS
#   function match a Python function of equal complexity and role.
# * McCabe counting includes short-circuit operators (&&, ||, ??) — mirroring the
#   Python analyzer counting `and`/`or` (BoolOp) — and additionally counts
#   ternaries, which are genuine branch points in JS/TS.
# ==========================================================

from typing import Dict, List, Optional

from backend.app.analysis.complexity_analyzer import ComplexityAnalyzer


# extension -> grammar key
_EXT_LANG = {
    ".js": "javascript", ".jsx": "javascript",
    ".ts": "typescript", ".tsx": "tsx",
}

# Cached per-process (each pool worker builds its own; tree-sitter Parser objects
# are C-backed and not shared across the pickling boundary).
_PARSERS: Dict[str, object] = {}
_TS_AVAILABLE: Optional[bool] = None
_WARNED = False


def _warn_once(msg: str) -> None:
    global _WARNED
    if not _WARNED:
        print(msg)
        _WARNED = True


def grammar_for_ext(ext: str) -> Optional[str]:
    return _EXT_LANG.get(ext.lower())


def _get_parser(grammar: str):
    """Return a cached tree-sitter Parser for `grammar`, or None if unavailable."""
    global _TS_AVAILABLE
    if _TS_AVAILABLE is False:
        return None
    if grammar in _PARSERS:
        return _PARSERS[grammar]
    try:
        from tree_sitter import Language, Parser
        if grammar == "javascript":
            import tree_sitter_javascript as ts
            lang = Language(ts.language())
        elif grammar == "typescript":
            import tree_sitter_typescript as ts
            lang = Language(ts.language_typescript())
        elif grammar == "tsx":
            import tree_sitter_typescript as ts
            lang = Language(ts.language_tsx())
        else:
            return None
        parser = Parser(lang)
        _PARSERS[grammar] = parser
        _TS_AVAILABLE = True
        return parser
    except Exception as e:  # ImportError, grammar mismatch, ABI/version skew
        _TS_AVAILABLE = False
        _warn_once(f"[js_structure] tree-sitter unavailable ({e!r}); "
                   f"JS/TS files fall back to no structural complexity metrics")
        return None


# ----------------------------------------------------------
# Grammar node vocabulary (verified against tree-sitter-javascript 0.25 /
# tree-sitter-typescript 0.23 — see the s-expression probe used to derive these).
# ----------------------------------------------------------

_FN_TYPES = {
    "function_declaration", "generator_function_declaration",
    "function_expression", "arrow_function", "method_definition",
}
_LOOP_TYPES = {
    "for_statement", "for_in_statement", "while_statement", "do_statement",
}
# Decision points that each add 1 to cyclomatic complexity (base 1).
_DECISION_TYPES = {
    "if_statement", "for_statement", "for_in_statement",
    "while_statement", "do_statement", "switch_case",
    "catch_clause", "ternary_expression",
}
_BRANCH_TYPES = {"if_statement", "switch_case", "catch_clause"}
_SHORT_CIRCUIT = {"&&", "||", "??"}


def _text(node) -> str:
    return node.text.decode("utf-8", "ignore")


def _fn_name(node) -> str:
    """Best-effort function name: declaration/method `name` field, else the
    variable / property / assignment target the function is bound to."""
    n = node.child_by_field_name("name")
    if n is not None:
        return _text(n)
    par = node.parent
    if par is not None:
        if par.type == "variable_declarator":
            nm = par.child_by_field_name("name")
            if nm is not None:
                return _text(nm)
        elif par.type == "pair":  # { handler: () => {} }
            key = par.child_by_field_name("key")
            if key is not None:
                return _text(key)
        elif par.type == "assignment_expression":  # obj.method = function () {}
            left = par.child_by_field_name("left")
            if left is not None:
                return _text(left)
    return "(anonymous)"


def _iter_functions(root):
    """Yield every function-like node in the tree (pre-order)."""
    stack = [root]
    while stack:
        node = stack.pop()
        if node.type in _FN_TYPES:
            yield node
        stack.extend(reversed(node.children))


def _measure(fn_node, fn_name: str):
    """Compute (cc, max_loop_depth, total_loops, branches, recursive) for ONE
    function, without descending into nested functions."""
    cc = 1
    branches = 0
    total_loops = 0
    max_depth = 0
    recursive = False

    # DFS carrying loop-nesting depth; stop at nested function boundaries.
    stack = [(fn_node, 0, True)]
    while stack:
        node, depth, is_root = stack.pop()
        t = node.type

        if t in _FN_TYPES and not is_root:
            continue  # nested function owns its own complexity

        if t in _DECISION_TYPES:
            cc += 1
            if t in _BRANCH_TYPES:
                branches += 1
        elif t == "binary_expression":
            op = node.child_by_field_name("operator")
            if op is not None and _text(op) in _SHORT_CIRCUIT:
                cc += 1

        if t == "call_expression":
            callee = node.child_by_field_name("function")
            if callee is not None and callee.type == "identifier" \
                    and _text(callee) == fn_name:
                recursive = True

        child_depth = depth
        if t in _LOOP_TYPES:
            total_loops += 1
            child_depth = depth + 1
            if child_depth > max_depth:
                max_depth = child_depth

        for c in node.children:
            stack.append((c, child_depth, False))

    return cc, max_depth, total_loops, branches, recursive


def analyze(code: str, ext: str, role: str = "utility") -> Dict[str, List]:
    """Structural analysis of a JS/TS source string.

    Returns {'functions': [names], 'complexity_metrics': [per-function dicts]}
    with the SAME per-function keys ComplexityAnalyzer.analyze_function emits, so
    repo_analyzer's existing aggregation treats JS/TS exactly like Python.

    Degraded (empty) result — never an exception — when the extension is not
    JS/TS, tree-sitter is unavailable, or parsing fails.
    """
    grammar = grammar_for_ext(ext)
    if grammar is None:
        return {"functions": [], "complexity_metrics": []}
    parser = _get_parser(grammar)
    if parser is None:
        return {"functions": [], "complexity_metrics": []}

    try:
        tree = parser.parse(bytes(code, "utf-8"))
    except Exception as e:  # pragma: no cover - defensive
        _warn_once(f"[js_structure] parse failed ({e!r}); no metrics for this file")
        return {"functions": [], "complexity_metrics": []}

    functions: List[str] = []
    metrics: List[Dict] = []
    helper = ComplexityAnalyzer()

    for fn in _iter_functions(tree.root_node):
        name = _fn_name(fn)
        cc, max_depth, total_loops, branches, recursive = _measure(fn, name)

        # Reuse the Python analyzer's role-aware verdicts for identical semantics.
        helper.reset_state()
        helper.cyclomatic_complexity = cc
        helper.max_loop_depth = max_depth
        helper.total_loops = total_loops
        helper.branches = branches
        helper.is_recursive = recursive

        metrics.append({
            "function": name,
            "cyclomatic_complexity": cc,
            "max_loop_depth": max_depth,
            "total_loops": total_loops,
            "branches": branches,
            "time_complexity": helper.estimate_time_complexity(),
            "recursive": recursive,
            "risk_level": helper.get_risk_level(cc, role=role),
            "hotspot": helper.is_hotspot(role=role),
        })
        if name and name != "(anonymous)":
            functions.append(name)

    return {
        "functions": list(dict.fromkeys(functions)),
        "complexity_metrics": metrics,
    }
