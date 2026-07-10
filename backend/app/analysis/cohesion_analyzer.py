# ==========================================================
# File: cohesion_analyzer.py
# Location: backend/app/analysis
#
# Purpose
# ----------------------------------------------------------
# Replaces the flat "file > 300 lines = bad" heuristic with a
# cohesion-gated size check.
#
# A file is only flagged as too large when it is BOTH long AND
# poorly cohesive:
#
#       line_count > 500  AND  module_cohesion < 0.40
#
# Rationale: Flask's sessions.py (~385 lines) and templating.py
# are long but highly cohesive; the old flat threshold flagged
# them as maintainability problems, which is a false positive.
# Size alone is not a defect. Size without cohesion is.
#
# Metrics
# ----------------------------------------------------------
# lcom4(class)      Lack of Cohesion of Methods (LCOM4): the
#                   number of connected components among a
#                   class's methods, where two methods are
#                   connected if they share an instance
#                   attribute or one calls the other.
#                   1 = perfectly cohesive. >1 = the class is
#                   really N classes in a trench coat.
#
# module_cohesion   Fraction of top-level function PAIRS that
#                   share at least one non-builtin identifier.
#                   1.0 = every pair related, 0.0 = none.
#                   Files with <= 1 top-level function are
#                   trivially cohesive (1.0) -- this is what
#                   protects class-heavy modules.
#
# Stdlib-only (ast, builtins).
# ==========================================================

from __future__ import annotations

import ast
import builtins
from dataclasses import dataclass
from typing import Dict, List, Optional, Set

# Size gate. Both conditions must hold before a file is flagged.
SIZE_LINE_THRESHOLD = 500
COHESION_THRESHOLD = 0.40

# Identifiers that connect everything and therefore say nothing
# about cohesion (len, print, range, str, ...).
_BUILTIN_NAMES = frozenset(dir(builtins))


# ==========================================================
# Union-Find (for LCOM4 connected components)
# ==========================================================

class _DisjointSet:
    def __init__(self, items) -> None:
        self._parent = {i: i for i in items}

    def find(self, i: str) -> str:
        root = i
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[i] != root:  # path compression, iterative
            self._parent[i], i = root, self._parent[i]
        return root

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self._parent[ra] = rb

    def component_count(self) -> int:
        return len({self.find(i) for i in self._parent})


# ==========================================================
# LCOM4
# ==========================================================

def _self_name(method: ast.AST) -> Optional[str]:
    """Name of the instance/class parameter, or None for staticmethods."""
    decorators = {
        d.id for d in getattr(method, "decorator_list", []) if isinstance(d, ast.Name)
    }
    if "staticmethod" in decorators:
        return None
    args = method.args.posonlyargs + method.args.args
    return args[0].arg if args else None


def _method_footprint(method: ast.AST, method_names: Set[str]) -> Set[str]:
    """
    Identifiers that tie a method to its siblings:
      - instance attributes accessed via self (`self.x` -> "attr:x")
      - calls to sibling methods (`self.m()` / `m()` -> "call:m")

    Deliberately NOT every ast.Attribute: two methods both calling
    os.path.join() are not cohesive, they just both use os.path.
    """
    self_nm = _self_name(method)
    found: Set[str] = set()

    for node in ast.walk(method):
        if isinstance(node, ast.Attribute) and self_nm is not None:
            if isinstance(node.value, ast.Name) and node.value.id == self_nm:
                if node.attr in method_names:
                    found.add(f"call:{node.attr}")
                else:
                    found.add(f"attr:{node.attr}")

        elif isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Name) and fn.id in method_names:
                found.add(f"call:{fn.id}")

    return found


def lcom4(class_node: ast.ClassDef) -> int:
    """
    Number of connected components among a class's methods.
    Returns 1 for classes with 0 or 1 methods (trivially cohesive).
    """
    methods = [n for n in class_node.body
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    if len(methods) <= 1:
        return 1

    method_names = {m.name for m in methods}
    footprints = {m.name: _method_footprint(m, method_names) for m in methods}

    ds = _DisjointSet(method_names)
    names = sorted(method_names)

    for i, a in enumerate(names):
        for b in names[i + 1:]:
            # direct call in either direction
            if f"call:{b}" in footprints[a] or f"call:{a}" in footprints[b]:
                ds.union(a, b)
                continue
            # shared instance attribute
            attrs_a = {x for x in footprints[a] if x.startswith("attr:")}
            attrs_b = {x for x in footprints[b] if x.startswith("attr:")}
            if attrs_a & attrs_b:
                ds.union(a, b)

    return ds.component_count()


# ==========================================================
# Module cohesion
# ==========================================================

def _function_identifiers(fn: ast.AST) -> Set[str]:
    """Non-builtin identifiers a top-level function touches."""
    names: Set[str] = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.Call):
            fnode = node.func
            if isinstance(fnode, ast.Name):
                names.add(fnode.id)
            elif isinstance(fnode, ast.Attribute):
                names.add(fnode.attr)
    return names - _BUILTIN_NAMES


def module_cohesion(tree: ast.AST) -> float:
    """
    Fraction of top-level function pairs sharing >= 1 identifier.

    Only TOP-LEVEL functions count. A module of <= 1 top-level
    function (e.g. a class-heavy module like Flask's sessions.py)
    is trivially cohesive and returns 1.0.
    """
    top_level = [n for n in tree.body
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    n = len(top_level)
    if n <= 1:
        return 1.0

    footprints = [_function_identifiers(f) for f in top_level]

    total_pairs = n * (n - 1) // 2
    connected = 0
    for i in range(n):
        for j in range(i + 1, n):
            if footprints[i] & footprints[j]:
                connected += 1

    return connected / total_pairs


# ==========================================================
# Public report
# ==========================================================

@dataclass(frozen=True)
class CohesionReport:
    file_path: str
    line_count: int
    module_cohesion: float
    class_scores: Dict[str, int]
    should_flag_size: bool
    flag_reason: str

    @property
    def low_cohesion_classes(self) -> List[str]:
        return sorted(name for name, score in self.class_scores.items() if score > 1)


def analyze_cohesion(source: str, file_path: str = "") -> CohesionReport:
    """
    Compute cohesion metrics and the size verdict for one file.

    Never raises on any input: an unparsable file returns a report
    with should_flag_size=False (we cannot judge what we cannot parse).
    """
    line_count = len(source.splitlines()) if source else 0

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return CohesionReport(
            file_path=file_path,
            line_count=line_count,
            module_cohesion=1.0,
            class_scores={},
            should_flag_size=False,
            flag_reason="parse error - cohesion check skipped",
        )

    mod_cohesion = module_cohesion(tree)

    class_scores: Dict[str, int] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            class_scores[node.name] = lcom4(node)

    should_flag = bool(line_count > SIZE_LINE_THRESHOLD
                       and mod_cohesion < COHESION_THRESHOLD)

    flag_reason = ""
    if should_flag:
        flag_reason = (
            f"File is {line_count} lines with low cohesion "
            f"({mod_cohesion:.2f} < {COHESION_THRESHOLD:.2f}) - "
            f"its top-level functions barely share state. Consider splitting."
        )

    return CohesionReport(
        file_path=file_path,
        line_count=line_count,
        module_cohesion=mod_cohesion,
        class_scores=class_scores,
        should_flag_size=should_flag,
        flag_reason=flag_reason,
    )


# JSON-serializable shape carried through the pipeline (file_data ->
# analyze_single_file -> final_output -> cache). This is the SINGLE
# source of truth for every "this file is too long" claim downstream:
# llm_service (issue, explanation, suggestion) and
# repository_review_engine (maintainability warning) all read
# should_flag_size rather than re-deriving a threshold of their own.
NO_SIZE_FLAG = {
    "line_count": 0,
    "module_cohesion": 1.0,
    "should_flag_size": False,
    "flag_reason": "",
    "low_cohesion_classes": [],
}


def size_verdict(source: str, file_path: str = "") -> Dict:
    """analyze_cohesion() reduced to a plain, cacheable dict."""
    r = analyze_cohesion(source, file_path)
    return {
        "line_count": r.line_count,
        "module_cohesion": round(r.module_cohesion, 3),
        "should_flag_size": r.should_flag_size,
        "flag_reason": r.flag_reason,
        "low_cohesion_classes": r.low_cohesion_classes,
    }
