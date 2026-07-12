# ==========================================================
# File: framework_detector.py
# Location: backend/app/analysis
#
# Purpose
# ----------------------------------------------------------
# Fingerprint the frameworks a repository actually uses, from its
# import statements — replacing the old filename-substring guess
# (security_analyzer._is_framework_context / Defect D) with real
# evidence: which modules import flask/fastapi/django/pytest/etc.
#
# Repo-level architecture intelligence: the detected web framework
# tells later analysis where request entrypoints live, and the test
# framework/ORM/CLI signals classify the codebase's shape.
# Stdlib-only (ast).
# ==========================================================

from __future__ import annotations

import ast
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List


# category -> {framework_name: (import-root prefixes)}
_SIGNATURES: Dict[str, Dict[str, tuple]] = {
    "web": {
        "flask": ("flask",),
        "fastapi": ("fastapi",),
        "django": ("django",),
        "starlette": ("starlette",),
        "tornado": ("tornado",),
        "pyramid": ("pyramid",),
        "sanic": ("sanic",),
        "bottle": ("bottle",),
        "aiohttp": ("aiohttp",),
        "falcon": ("falcon",),
    },
    "test": {
        "pytest": ("pytest", "_pytest"),
        "unittest": ("unittest",),
        "nose": ("nose",),
    },
    "cli": {
        "click": ("click",),
        "typer": ("typer",),
        "argparse": ("argparse",),
    },
    "orm": {
        "sqlalchemy": ("sqlalchemy",),
        "django-orm": ("django.db",),
        "peewee": ("peewee",),
        "tortoise": ("tortoise",),
        "mongoengine": ("mongoengine",),
    },
    "task": {
        "celery": ("celery",),
        "rq": ("rq",),
        "dramatiq": ("dramatiq",),
    },
}


@dataclass
class FrameworkHit:
    name: str
    category: str
    files: List[str] = field(default_factory=list)   # files importing it

    @property
    def confidence(self) -> float:
        # more importing files -> higher confidence, capped
        return min(0.5 + 0.1 * len(self.files), 0.99)


def _import_roots(tree: ast.AST) -> set:
    """Top-level and dotted import roots in a module (e.g. 'django.db')."""
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                roots.add(a.name)
                roots.add(a.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                roots.add(node.module)
                roots.add(node.module.split(".")[0])
    return roots


def _matches(roots: set, prefixes: tuple) -> bool:
    for r in roots:
        for p in prefixes:
            if r == p or r.startswith(p + "."):
                return True
    return False


def detect_frameworks(sources: Dict[str, str]) -> Dict[str, List[FrameworkHit]]:
    """
    Return detected frameworks grouped by category, each with the files that
    import it. Unparsable files are skipped. Never raises.
    """
    hits: Dict[tuple, FrameworkHit] = {}

    for path, code in sources.items():
        try:
            tree = ast.parse(code)
        except SyntaxError:
            continue
        roots = _import_roots(tree)
        for category, frameworks in _SIGNATURES.items():
            for name, prefixes in frameworks.items():
                if _matches(roots, prefixes):
                    key = (category, name)
                    if key not in hits:
                        hits[key] = FrameworkHit(name=name, category=category)
                    hits[key].files.append(path)

    out: Dict[str, List[FrameworkHit]] = defaultdict(list)
    for (category, _), hit in hits.items():
        out[category].append(hit)
    for category in out:
        out[category].sort(key=lambda h: (-len(h.files), h.name))
    return dict(out)


def primary_web_framework(sources: Dict[str, str]) -> str:
    """The web framework importing the most files, or 'none'."""
    web = detect_frameworks(sources).get("web", [])
    return web[0].name if web else "none"


def summarize_frameworks(sources: Dict[str, str]) -> Dict[str, List[str]]:
    """Flat {category: [framework names]} view for a report payload."""
    detected = detect_frameworks(sources)
    return {cat: [h.name for h in hits] for cat, hits in detected.items()}
