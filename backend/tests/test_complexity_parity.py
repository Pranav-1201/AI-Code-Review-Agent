"""Backlog B2 — reconcile our cyclomatic complexity with radon's.

Measured with radon 6 in a throwaway venv, before any change:

    review_repository      ours 33   radon 58   gap +25
    analyze_dependencies   ours 75   radon 68   gap  -7

Both gaps resolved exactly, in opposite directions:

  * +25 = 14 comprehension generators + 6 comprehension filters + 5
    ternaries. A comprehension with a filter is a loop and a branch; both
    are decision points under McCabe and both were being skipped. The
    existing comment justified skipping comprehensions to stop them
    inflating *nesting depth* — a different metric that happens to share
    this visitor. Complexity and depth are now separated.

  * -7 = exactly the seven decision points of the nested `_add_dep`
    function (extracted to `_DependencyCollector.add` by B1; this docstring
    records the measurement as it stood).
    We folded a nested function's complexity into its parent;
    radon scores each function on its own body. Attributing a helper's
    branches to its enclosing function makes the enclosing function look
    worse than it reads.
"""
import ast

import pytest

from backend.app.analysis.complexity_analyzer import ComplexityAnalyzer


def cc(source: str, name: str = "f") -> int:
    tree = ast.parse(source)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
              and n.name == name)
    return ComplexityAnalyzer().analyze_function(fn)["cyclomatic_complexity"]


def depth(source: str, name: str = "f") -> int:
    tree = ast.parse(source)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
              and n.name == name)
    return ComplexityAnalyzer().analyze_function(fn)["max_loop_depth"]


def test_a_straight_line_function_is_one():
    assert cc("def f():\n    return 1\n") == 1


def test_an_if_counts():
    assert cc("def f(x):\n    if x:\n        return 1\n    return 2\n") == 2


# ---- gap 1: comprehensions and ternaries were not counted ----

def test_a_comprehension_counts_as_a_decision_point():
    assert cc("def f(xs):\n    return [x for x in xs]\n") == 2


def test_a_comprehension_filter_counts_too():
    assert cc("def f(xs):\n    return [x for x in xs if x]\n") == 3


def test_a_nested_comprehension_counts_each_generator():
    assert cc("def f(xs):\n    return [y for x in xs for y in x]\n") == 3


def test_a_ternary_counts():
    assert cc("def f(x):\n    return 1 if x else 2\n") == 2


def test_generator_and_dict_and_set_comprehensions_all_count():
    assert cc("def f(xs):\n    return sum(x for x in xs)\n") == 2
    assert cc("def f(xs):\n    return {x: 1 for x in xs}\n") == 2
    assert cc("def f(xs):\n    return {x for x in xs}\n") == 2


def test_a_comprehension_still_does_not_inflate_loop_depth():
    """The reason comprehensions were skipped in the first place.

    A list comprehension inside a while loop was reported as depth 2 and
    the file came back O(n^2). Complexity counts it; depth must not.
    """
    source = (
        "def f(xs):\n"
        "    while xs:\n"
        "        ys = [x for x in xs]\n"
        "    return ys\n"
    )
    assert depth(source) == 1
    assert cc(source) == 3   # 1 + while + comprehension


# ---- gap 2: a nested function's branches belonged to it, not its parent ----

def test_a_nested_function_does_not_inflate_its_parent():
    source = (
        "def f(xs):\n"
        "    def helper(y):\n"
        "        if y:\n"
        "            return 1\n"
        "        if y > 2:\n"
        "            return 2\n"
        "        return 3\n"
        "    return helper(xs)\n"
    )
    assert cc(source) == 1


def test_the_parent_still_counts_its_own_branches():
    source = (
        "def f(xs):\n"
        "    def helper(y):\n"
        "        if y:\n"
        "            return 1\n"
        "        return 2\n"
        "    if xs:\n"
        "        return helper(xs)\n"
        "    return 0\n"
    )
    assert cc(source) == 2


def test_the_nested_function_is_still_scored_on_its_own():
    source = (
        "def f(xs):\n"
        "    def helper(y):\n"
        "        if y:\n"
        "            return 1\n"
        "        return 2\n"
        "    return helper(xs)\n"
    )
    assert cc(source, "helper") == 2


def test_a_lambda_still_belongs_to_its_enclosing_function():
    """radon attributes a lambda to the function it is written in."""
    assert cc("def f(xs):\n    return sorted(xs, key=lambda v: v.a)\n") == 1
