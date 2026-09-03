"""Backlog B4 — `most_reused_module` must name a module of the user's own.

Measured against this repository before the fix: the answer was `os`, with
`sys` and `typing` next. The standard library always wins a raw in-degree
count, so the insight said nothing about the codebase being analysed. The
first-party answer here is `backend.app.services.security_analyzer`.
"""
from backend.app.services.repository_review_engine import most_reused_first_party


def _graph(links):
    return {
        "nodes": [{"id": n} for n in {l["source"] for l in links}
                  | {l["target"] for l in links}],
        "links": links,
    }


# The repository's own files. This is what makes "first party" decidable at
# all: in the graph, `requests` and a local module look identical.
MYAPP_FILES = [
    "myapp/services/core.py",
    "myapp/util.py",
    "a.py", "b.py", "c.py", "d.py", "e.py",
    "helpers.py",
]


def test_the_standard_library_never_wins():
    graph = _graph([
        {"source": "a.py", "target": "os"},
        {"source": "b.py", "target": "os"},
        {"source": "c.py", "target": "os"},
        {"source": "d.py", "target": "sys"},
        {"source": "e.py", "target": "myapp.services.core"},
    ])
    assert most_reused_first_party(graph, MYAPP_FILES) == "myapp.services.core"


def test_a_third_party_package_never_wins():
    """Not stdlib, still not the user's code."""
    graph = _graph([
        {"source": "a.py", "target": "requests"},
        {"source": "b.py", "target": "requests"},
        {"source": "c.py", "target": "numpy"},
        {"source": "d.py", "target": "myapp.util"},
    ])
    assert most_reused_first_party(graph, MYAPP_FILES) == "myapp.util"


def test_a_local_single_segment_module_still_counts():
    """`import helpers` next to the file that imports it is first-party."""
    graph = _graph([
        {"source": "a.py", "target": "os"},
        {"source": "b.py", "target": "helpers.py"},
        {"source": "c.py", "target": "helpers.py"},
    ])
    assert most_reused_first_party(graph, MYAPP_FILES) == "helpers.py"


def test_a_repository_with_no_first_party_imports_says_none():
    graph = _graph([
        {"source": "a.py", "target": "os"},
        {"source": "b.py", "target": "sys"},
    ])
    assert most_reused_first_party(graph, MYAPP_FILES) == "None"


def test_an_empty_graph_says_none():
    assert most_reused_first_party({}, MYAPP_FILES) == "None"
    assert most_reused_first_party({"nodes": [], "links": []}, MYAPP_FILES) == "None"


def test_ties_break_deterministically():
    """Two modules at the same in-degree must not reorder between runs."""
    links = [
        {"source": "a.py", "target": "myapp.b"},
        {"source": "c.py", "target": "myapp.a"},
    ]
    assert most_reused_first_party(_graph(links), MYAPP_FILES) == "myapp.a"
    assert most_reused_first_party(_graph(list(reversed(links))), MYAPP_FILES) == "myapp.a"
