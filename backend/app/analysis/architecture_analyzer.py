# ==========================================================
# File: architecture_analyzer.py
# Location: backend/app/analysis
#
# Purpose
# ----------------------------------------------------------
# Repository-level architecture smells:
#   • God objects   — large, low-cohesion classes doing too much
#                     (method count + LCOM4 disjoint responsibilities)
#   • Layer violations — a lower architectural layer importing a
#                     higher one (e.g. a model importing an API route)
#
# Cycles are already covered elsewhere (call_graph.find_call_cycles for
# function recursion, call_graph.detect_circular_imports for module
# cycles); this module adds the two structural smells that need class
# cohesion and path-derived layering. Stdlib-only (ast).
# ==========================================================

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Dict, List, Optional

from backend.app.analysis.cohesion_analyzer import lcom4
from backend.app.analysis.call_graph import (
    build_import_graph, _module_key, _resolve_local_module,
)

# God-object thresholds (see analyze note): a big class is a god object when
# it is large AND its methods split into several unrelated responsibility
# clusters, or when it is very large regardless of cohesion.
_GOD_METHODS = 12
_GOD_LCOM4 = 3
_GOD_METHODS_HARD = 25

# Architectural layers, lowest (0) to highest. A lower layer must not import
# a higher one. Matched against path segments.
_LAYER_KEYWORDS = [
    (0, ("model", "models", "entity", "entities", "schema", "schemas",
         "domain", "dto")),
    (1, ("repository", "repositories", "dao", "store", "dataaccess")),
    (2, ("service", "services", "usecase", "usecases", "business",
         "logic", "engine")),
    (3, ("api", "routes", "route", "controller", "controllers", "view",
         "views", "handler", "handlers", "endpoint", "endpoints")),
]
_LAYER_NAME = {0: "model", 1: "repository", 2: "service", 3: "api"}


@dataclass
class GodObject:
    class_name: str
    file: str
    line: int
    method_count: int
    lcom4: int
    reason: str


@dataclass
class LayerViolation:
    importer: str          # module key
    importee: str          # module key
    importer_layer: str
    importee_layer: str
    line: int


def detect_god_objects(sources: Dict[str, str]) -> List[GodObject]:
    """Classes that are large and low-cohesion. Never raises."""
    found: List[GodObject] = []
    for path, code in sources.items():
        try:
            tree = ast.parse(code)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            methods = [n for n in node.body
                       if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            mcount = len(methods)
            if mcount < 3:
                continue
            cohesion = lcom4(node)
            reason = None
            if mcount >= _GOD_METHODS_HARD:
                reason = f"{mcount} methods (very large class)"
            elif mcount >= _GOD_METHODS and cohesion >= _GOD_LCOM4:
                reason = (f"{mcount} methods split into {cohesion} unrelated "
                          f"responsibility clusters (LCOM4={cohesion})")
            if reason:
                found.append(GodObject(
                    class_name=node.name, file=path, line=node.lineno,
                    method_count=mcount, lcom4=cohesion, reason=reason,
                ))
    return sorted(found, key=lambda g: (-g.method_count, g.file))


def _layer_of(module_key: str) -> Optional[int]:
    segments = set(module_key.replace("::", ".").split("."))
    for level, keywords in _LAYER_KEYWORDS:
        if segments & set(keywords):
            return level
    return None


def detect_layer_violations(sources: Dict[str, str]) -> List[LayerViolation]:
    """
    A layer violation is a lower layer importing a strictly higher one
    (e.g. a model importing an api route). Only local modules with an
    inferable layer are considered. Never raises.
    """
    graph = build_import_graph(sources)
    nodes = {_module_key(p) for p in sources}
    violations: List[LayerViolation] = []

    for path, edges in graph.items():
        importer_key = _module_key(path)
        importer_layer = _layer_of(importer_key)
        if importer_layer is None:
            continue
        for edge in edges:
            target = _resolve_local_module(edge.importee, nodes)
            if not target or target == importer_key:
                continue
            importee_layer = _layer_of(target)
            if importee_layer is None:
                continue
            if importer_layer < importee_layer:
                violations.append(LayerViolation(
                    importer=importer_key, importee=target,
                    importer_layer=_LAYER_NAME[importer_layer],
                    importee_layer=_LAYER_NAME[importee_layer],
                    line=edge.line,
                ))
    return sorted(violations, key=lambda v: (v.importer, v.line))


def analyze_architecture(sources: Dict[str, str]) -> Dict[str, list]:
    """Combined architecture-smell payload for a repository report."""
    return {
        "god_objects": [g.__dict__ for g in detect_god_objects(sources)],
        "layer_violations": [v.__dict__ for v in detect_layer_violations(sources)],
    }
