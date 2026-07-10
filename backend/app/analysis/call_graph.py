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