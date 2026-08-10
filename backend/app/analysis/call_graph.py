# ==========================================================
# File: call_graph.py
# Location: backend/app/analysis
#
# Purpose
# ----------------------------------------------------------
# Builds a function call graph for a repository by analyzing
# Python source code using AST.
#
# The call graph represents which functions are invoked
# inside each file.
#
# Example Output
# ----------------------------------------------------------
# {
#     "utils.py": ["load_data", "process_data"],
#     "model.py": ["predict", "numpy"]
# }
#
# This structure helps the AI analysis system understand
# dependencies between components before performing
# embedding, RAG retrieval, or code review.
# ==========================================================

import ast
import sys
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional


# ==========================================================
# Function Call Extraction
# ==========================================================
def extract_function_calls(code: str) -> List[str]:
    """
    Extract all function calls from a single Python file.

    Parameters
    ----------
    code : str
        Python source code.

    Returns
    -------
    List[str]
        List of called function names.
    """

    try:
        tree = ast.parse(code)
    except SyntaxError:
        # Prevent crash if file has invalid syntax
        return []

    calls: List[str] = []

    # Walk through AST nodes
    for node in ast.walk(tree):

        if isinstance(node, ast.Call):

            # Example: foo()
            if isinstance(node.func, ast.Name):
                calls.append(node.func.id)

            # Example: obj.method()
            elif isinstance(node.func, ast.Attribute):
                calls.append(node.func.attr)

    # Remove duplicates while preserving order
    calls = list(dict.fromkeys(calls))

    return calls


# ==========================================================
# Repository-Level Call Graph Builder
# ==========================================================
def build_call_graph(files_data: List[Dict]) -> Dict[str, List[str]]:
    """
    Construct a call graph for an entire repository.

    Parameters
    ----------
    files_data : List[Dict]
        List containing repository file data.
        Each item must contain:
        {
            "file_name": str,
            "content": str
        }

    Returns
    -------
    Dict[str, List[str]]
        Mapping of file name → functions called in that file.
    """

    graph: Dict[str, List[str]] = defaultdict(list)

    for file in files_data:

        file_name = file.get("file_name")
        code = file.get("content", "")

        calls = extract_function_calls(code)

        graph[file_name].extend(calls)

    return dict(graph)


# ==========================================================
# Phase 2: Import Graph
# ----------------------------------------------------------
# Builds a module-level import graph and answers two questions
# the file-level call graph cannot:
#   - detect_circular_imports(): which modules form import cycles
#   - detect_unused_imports():   which imports are never referenced
#
# __init__.py re-export whitelist
# ----------------------------------------------------------
# A package __init__.py exists to re-export names from its
# submodules:
#
#       # pkg/__init__.py
#       from pkg.core import Engine     # re-export, not "unused"
#
# and importing a submodule from __init__ routinely produces a
# package<->submodule edge that is NOT a real dependency cycle.
# Both checks therefore treat __init__ files specially:
#   - unused: never flag an import inside an __init__ file
#   - cycles: __init__ modules do not originate cycle edges
# ==========================================================


@dataclass(frozen=True)
class ImportEdge:
    importer: str            # file path of the importing module
    importee: str            # dotted module/name being imported
    alias: Optional[str]     # `import x as alias` / `from m import n as alias`
    is_from_import: bool
    is_wildcard: bool
    line: int


def _is_init_file(path: str) -> bool:
    return path.replace("\\", "/").split("/")[-1] == "__init__.py"


def build_import_graph(sources: Dict[str, str]) -> Dict[str, List[ImportEdge]]:
    """
    Parse each {file_path: source} and return the import edges per file.
    Unparsable files map to an empty edge list (never raises).
    """
    graph: Dict[str, List[ImportEdge]] = {}

    for path, source in sources.items():
        edges: List[ImportEdge] = []
        try:
            tree = ast.parse(source)
        except SyntaxError:
            graph[path] = []
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    edges.append(ImportEdge(
                        importer=path, importee=alias.name, alias=alias.asname,
                        is_from_import=False, is_wildcard=False, line=node.lineno,
                    ))
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    wildcard = alias.name == "*"
                    importee = f"{module}.{alias.name}" if module else alias.name
                    edges.append(ImportEdge(
                        importer=path, importee=importee, alias=alias.asname,
                        is_from_import=True, is_wildcard=wildcard, line=node.lineno,
                    ))
        graph[path] = edges

    return graph


def _module_key(path: str) -> str:
    """
    Reduce a file path to a dotted module key for cycle matching:
      pkg/core/engine.py -> pkg.core.engine
      pkg/__init__.py    -> pkg
    """
    norm = path.replace("\\", "/")
    if norm.endswith(".py"):
        norm = norm[:-3]
    parts = [p for p in norm.split("/") if p]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _resolve_local_module(importee: str, nodes: set) -> Optional[str]:
    """
    Map an importee ('pkg.core.Engine', 'pkg.core') to a local module key,
    trying the longest prefix first so 'pkg.core.Engine' resolves to the
    module 'pkg.core' rather than the package 'pkg'.
    """
    parts = importee.split(".")
    for end in range(len(parts), 0, -1):
        candidate = ".".join(parts[:end])
        if candidate in nodes:
            return candidate
    return None


def _dedup_cycles(cycles: List[List[str]]) -> List[List[str]]:
    seen = set()
    unique: List[List[str]] = []
    for cyc in cycles:
        if not cyc:
            continue
        start = cyc.index(min(cyc))
        canonical = tuple(cyc[start:] + cyc[:start])
        if canonical not in seen:
            seen.add(canonical)
            unique.append(list(canonical))
    return unique


def detect_circular_imports(
    import_graph: Dict[str, List[ImportEdge]]
) -> List[List[str]]:
    """
    Return import cycles as lists of module keys.

    Only edges between modules present in `import_graph` count -- an
    import of an external library (requests, os) can never form a cycle
    with local code. Edges ORIGINATING in an __init__ file are excluded
    (see the re-export whitelist note above), so a package importing its
    own submodule is not reported as a cycle.
    """
    key_to_path = {_module_key(p): p for p in import_graph}
    nodes = set(key_to_path)

    adj: Dict[str, set] = {k: set() for k in nodes}
    for path, edges in import_graph.items():
        if _is_init_file(path):
            continue  # whitelist: __init__ re-exports do not originate cycles
        importer_key = _module_key(path)
        for edge in edges:
            target = _resolve_local_module(edge.importee, nodes)
            if target and target != importer_key:
                adj[importer_key].add(target)

    WHITE, GRAY, BLACK = 0, 1, 2
    color = {k: WHITE for k in nodes}
    path_stack: List[str] = []
    cycles: List[List[str]] = []

    def dfs(u: str) -> None:
        color[u] = GRAY
        path_stack.append(u)
        for v in sorted(adj[u]):
            if color[v] == WHITE:
                dfs(v)
            elif color[v] == GRAY:  # back edge -> cycle
                cycles.append(path_stack[path_stack.index(v):])
        path_stack.pop()
        color[u] = BLACK

    old_limit = sys.getrecursionlimit()
    sys.setrecursionlimit(max(old_limit, len(nodes) + 100))
    try:
        for k in sorted(nodes):
            if color[k] == WHITE:
                dfs(k)
    finally:
        sys.setrecursionlimit(old_limit)

    return _dedup_cycles(cycles)


# side-effect / re-export modules that are "used" merely by being imported
_SIDE_EFFECT_ENDINGS = (
    "logging", "warnings", "typing_extensions", "__future__",
    "dotenv", "django.conf",
)


def detect_unused_imports(
    tree: ast.AST,
    edges: List[ImportEdge],
    file_path: str,
) -> List[ImportEdge]:
    """
    Return the imports in `edges` that are never referenced in `tree`.

    Whitelist (never reported):
      - anything in an __init__ file (re-export surface)
      - wildcard imports (cannot tell what they bind)
      - known side-effect modules (logging, warnings, __future__, ...)

    Alias-aware (Fix F): `import numpy as np` is "used" iff `np` appears,
    not `numpy`.
    """
    if _is_init_file(file_path):
        return []

    used: set = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            used.add(node.id)
        elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            used.add(node.value.id)

    unused: List[ImportEdge] = []
    for edge in edges:
        if edge.is_wildcard:
            continue
        if any(edge.importee.endswith(s) for s in _SIDE_EFFECT_ENDINGS):
            continue
        # Bound name is the alias if present, else the leaf of the import
        # path (Fix F: alias-aware, not the dotted module name).
        bound = edge.alias if edge.alias else edge.importee.split(".")[-1]
        if bound not in used:
            unused.append(edge)

    return unused


# ==========================================================
# Phase 4: Interprocedural Call Graph (two-pass def/resolve)
# ----------------------------------------------------------
# Real function->function edges across a repository, replacing the
# file-level name-bag (build_call_graph) for dead-code and cycle
# analysis. Two passes:
#
#   Pass 1  collect every function/method DEFINITION with a qualified
#           name (module::Class.method or module::func) plus metadata
#           (decorators, entrypoint-ness, whether its class uses
#           dynamic dispatch).
#   Pass 2  resolve each call site to definition(s):
#             name()          -> module-local def, else same-name defs
#             self.m()        -> method m in the SAME class (precise)
#             obj.m()         -> any method named m (conservative)
#             getattr(o,x)()  -> UNRESOLVED (dynamic) — no fabricated edge
#
# Dynamic-dispatch awareness (the dogfooding edge case): this codebase's
# own analyzers subclass ast.NodeVisitor and are dispatched via
# self.visit(node) -> getattr(self, "visit_"+T)(). A naive detector would
# flag every visit_* method as dead. Classes that use getattr(self, ...)()
# or subclass a *Visitor base are marked dynamic; their methods are never
# reported dead. Monkey-patching is not modelled — this codebase does none
# in app code (only tests use mock.patch, which does not affect the graph).
# ==========================================================

from typing import Set as _Set  # local alias; module already imports Dict/List/Optional


# Decorator name endings that mark a function as an externally-invoked
# entrypoint (web route / CLI command / task) — called by a framework,
# not by name in-code, so they must never be reported as dead.
_ENTRYPOINT_DECORATOR_HINTS = (
    "route", "get", "post", "put", "delete", "patch", "options", "head",
    "websocket", "middleware", "task", "command", "cli", "callback",
    "on_event", "exception_handler", "api_view", "action", "step",
    "fixture", "hookimpl",
)

# Bases whose subclasses dispatch dynamically (getattr-based visit).
_DYNAMIC_DISPATCH_BASES = ("NodeVisitor", "NodeTransformer", "Visitor")


@dataclass
class FuncNode:
    qualname: str                    # module::Class.method | module::func
    module: str
    name: str                        # simple name
    class_name: Optional[str]
    lineno: int
    decorators: List[str]
    is_entrypoint: bool
    in_dynamic_class: bool           # class dispatches via getattr -> never dead


@dataclass
class CallGraph:
    nodes: Dict[str, FuncNode]           # qualname -> node
    edges: Dict[str, "_Set[str]"]        # caller qualname -> callee qualnames
    name_references: "_Set[str]"         # simple names used as a Load anywhere
    unresolved_dynamic: int              # count of getattr()/computed call sites


def _dotted_name(node: ast.AST) -> str:
    """Best-effort dotted string for a decorator/attribute expression."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_dotted_name(node.value)}.{node.attr}"
    if isinstance(node, ast.Call):
        return _dotted_name(node.func)
    return ""


def _is_dunder(name: str) -> bool:
    return name.startswith("__") and name.endswith("__")


def _class_is_dynamic(cls: ast.ClassDef) -> bool:
    """A class dispatches dynamically if it subclasses a *Visitor base or
    its body contains getattr(self, ...)()-style dispatch."""
    for base in cls.bases:
        if _dotted_name(base).split(".")[-1] in _DYNAMIC_DISPATCH_BASES:
            return True
    for node in ast.walk(cls):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id == "getattr":
            # getattr(self, ...) / getattr(cls, ...) -> dynamic method access
            if node.args and isinstance(node.args[0], ast.Name) \
                    and node.args[0].id in ("self", "cls"):
                return True
    return False


def _decorator_is_entrypoint(decorators: List[str]) -> bool:
    for d in decorators:
        leaf = d.split(".")[-1].lower()
        if leaf in _ENTRYPOINT_DECORATOR_HINTS:
            return True
    return False


def _import_time_nodes(tree: ast.AST):
    """Yield nodes that execute at IMPORT time, pruning function bodies.

    Module-level statements and class bodies both run on import, so both are
    walked. Function bodies are skipped because pass 2 already attributes those
    to their own caller — descending into them here would credit a module with
    calls it does not actually make until something invokes the function, which
    is precisely the over-approximation that would stop dead code being found
    at all.

    A function's decorator list and default arguments DO evaluate at import
    time, but they are left to pass 2's name_references handling rather than
    duplicated here.
    """
    stack = [tree]
    while stack:
        current = stack.pop()
        for child in ast.iter_child_nodes(current):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            yield child
            stack.append(child)


def build_interprocedural_graph(sources: Dict[str, str]) -> CallGraph:
    """
    Build a function-level call graph across {file_path: source}.
    Unparsable files are skipped. Never raises.
    """
    nodes: Dict[str, FuncNode] = {}
    name_references: _Set[str] = set()
    # (body, caller_qualname, module, class_ctx) records for pass 2
    func_bodies: List[tuple] = []
    # module -> {simple_name: qualname} for module-local resolution
    module_funcs: Dict[str, Dict[str, str]] = defaultdict(dict)
    # class_qual -> {method_name: qualname}
    class_methods: Dict[str, Dict[str, str]] = defaultdict(dict)
    # simple name -> set of qualnames (cross-module fallback)
    name_index: Dict[str, _Set[str]] = defaultdict(set)
    # (tree, module) for the import-time pass
    module_trees: List[tuple] = []

    # -------- Pass 1: definitions --------
    for path, source in sources.items():
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        module = _module_key(path)

        def visit(node, class_ctx: Optional[str], dynamic_ctx: bool):
            for child in ast.iter_child_nodes(node):
                if isinstance(child, ast.ClassDef):
                    dyn = dynamic_ctx or _class_is_dynamic(child)
                    new_ctx = (class_ctx + "." if class_ctx else "") + child.name
                    visit(child, new_ctx, dyn)
                elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    decos = [_dotted_name(d) for d in child.decorator_list]
                    if class_ctx:
                        qual = f"{module}::{class_ctx}.{child.name}"
                    else:
                        qual = f"{module}::{child.name}"
                    entry = (_decorator_is_entrypoint(decos)
                             or _is_dunder(child.name)
                             or (class_ctx is None and child.name == "main"))
                    nodes[qual] = FuncNode(
                        qualname=qual, module=module, name=child.name,
                        class_name=class_ctx, lineno=child.lineno,
                        decorators=decos, is_entrypoint=entry,
                        in_dynamic_class=dynamic_ctx,
                    )
                    name_index[child.name].add(qual)
                    if class_ctx:
                        class_methods[f"{module}::{class_ctx}"][child.name] = qual
                    else:
                        module_funcs[module][child.name] = qual
                    func_bodies.append((child, qual, module, class_ctx))
                    # nested functions/classes keep the same class context
                    visit(child, class_ctx, dynamic_ctx)
                else:
                    visit(child, class_ctx, dynamic_ctx)

        visit(tree, None, False)
        module_trees.append((tree, module))

    # -------- Pass 2: resolve calls --------
    edges: Dict[str, _Set[str]] = {q: set() for q in nodes}
    unresolved = 0

    # -------- Pass 1b: module-level (import-time) code --------
    #
    # Pass 2 walks func_bodies only, so anything executed at IMPORT time was
    # invisible to the graph: the `if __name__ == "__main__":` block, module-
    # level registration, class-body assignments. A function called only from
    # there had no incoming edge and was reported dead — the false positive
    # that held dead_function precision at 0.67 (fixture F6), and which would
    # flag the entrypoint of essentially every CLI ever written.
    #
    # Import-time code is attributed to a synthetic "<module>" caller. That key
    # is intentionally absent from `nodes`: find_dead_functions only unions
    # edges.values(), and find_call_cycles iterates nodes, so the synthetic
    # caller adds reachability without becoming a graph node itself.
    for tree, module in module_trees:
        synthetic = f"{module}::<module>"
        edges.setdefault(synthetic, set())
        for n in _import_time_nodes(tree):
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
                name_references.add(n.id)
            if not isinstance(n, ast.Call):
                continue
            fn = n.func
            if isinstance(fn, ast.Name):
                nm = fn.id
                if nm in module_funcs.get(module, {}):
                    edges[synthetic].add(module_funcs[module][nm])
                elif nm in name_index:
                    edges[synthetic] |= name_index[nm]
            elif isinstance(fn, ast.Attribute) and fn.attr in name_index:
                edges[synthetic] |= name_index[fn.attr]

    for body, caller_qual, module, class_ctx in func_bodies:
        class_qual = f"{module}::{class_ctx}" if class_ctx else None
        for n in ast.walk(body):
            # any Load of a def name keeps that def alive (callbacks, decorators)
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
                name_references.add(n.id)
            if not isinstance(n, ast.Call):
                continue
            fn = n.func
            if isinstance(fn, ast.Name):
                nm = fn.id
                if nm in module_funcs.get(module, {}):
                    edges[caller_qual].add(module_funcs[module][nm])
                elif nm in name_index:
                    edges[caller_qual] |= name_index[nm]
            elif isinstance(fn, ast.Attribute):
                attr = fn.attr
                recv = fn.value
                if isinstance(recv, ast.Name) and recv.id in ("self", "cls") and class_qual:
                    if attr in class_methods.get(class_qual, {}):
                        edges[caller_qual].add(class_methods[class_qual][attr])
                    elif attr in name_index:
                        edges[caller_qual] |= name_index[attr]
                else:
                    if attr in name_index:
                        edges[caller_qual] |= name_index[attr]
            else:
                # getattr(...)(), computed call, subscript call -> dynamic
                unresolved += 1

    return CallGraph(nodes=nodes, edges=edges,
                     name_references=name_references,
                     unresolved_dynamic=unresolved)


def find_dead_functions(graph: CallGraph) -> List[FuncNode]:
    """
    Functions defined but provably never used. A function is DEAD when it has
    no incoming call edge AND its simple name is never referenced as a value
    anywhere (callback/decorator use) AND it is not an entrypoint, a dunder,
    or a method of a dynamic-dispatch class.

    Conservative by construction: any uncertainty (cross-module same-name call,
    dynamic dispatch, framework entrypoint) keeps a function ALIVE. It reports
    false negatives before false positives — it will not cry wolf on the
    NodeVisitor visit_* methods this codebase itself relies on.
    """
    called: _Set[str] = set()
    for callees in graph.edges.values():
        called |= callees

    dead: List[FuncNode] = []
    for qual, node in graph.nodes.items():
        if qual in called:
            continue
        if node.is_entrypoint or node.in_dynamic_class or _is_dunder(node.name):
            continue
        if node.name in graph.name_references:
            continue
        dead.append(node)
    return sorted(dead, key=lambda n: (n.module, n.lineno))


def find_call_cycles(graph: CallGraph) -> List[List[str]]:
    """
    Strongly-connected components of size > 1 (mutual recursion) plus direct
    self-recursion, via Tarjan's algorithm. Returns each cycle as a list of
    qualnames. Stdlib only; iterative to avoid recursion-limit issues.
    """
    index_counter = [0]
    stack: List[str] = []
    on_stack: Dict[str, bool] = {}
    index: Dict[str, int] = {}
    lowlink: Dict[str, int] = {}
    result: List[List[str]] = []
    edges = graph.edges

    def strongconnect(v: str):
        work = [(v, iter(sorted(edges.get(v, ()))))]
        index[v] = lowlink[v] = index_counter[0]
        index_counter[0] += 1
        stack.append(v); on_stack[v] = True
        while work:
            node, it = work[-1]
            advanced = False
            for w in it:
                if w not in graph.nodes:
                    continue
                if w not in index:
                    index[w] = lowlink[w] = index_counter[0]
                    index_counter[0] += 1
                    stack.append(w); on_stack[w] = True
                    work.append((w, iter(sorted(edges.get(w, ())))))
                    advanced = True
                    break
                elif on_stack.get(w):
                    lowlink[node] = min(lowlink[node], index[w])
            if advanced:
                continue
            if lowlink[node] == index[node]:
                comp = []
                while True:
                    w = stack.pop(); on_stack[w] = False
                    comp.append(w)
                    if w == node:
                        break
                if len(comp) > 1 or (node in edges.get(node, set())):
                    result.append(sorted(comp))
            work.pop()
            if work:
                parent = work[-1][0]
                lowlink[parent] = min(lowlink[parent], lowlink[node])

    for v in list(graph.nodes):
        if v not in index:
            strongconnect(v)
    return result