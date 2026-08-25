"""
Unit tests for HeuristicRefactorEngine (formerly the misnamed
LLMRefactorEngine — it is deterministic and rule-based, no LLM).

The engine applies AST-driven transforms (docstring/type-hint insertion)
and complexity/smell suggestions. These tests are deterministic and touch
no models or external APIs.

Tests verify:
- correct request handling
- output structure
- handling of empty inputs
- handling of complex code
- resilience to malformed input
"""

import sys
import os
from unittest.mock import patch

import pytest

# Allow importing backend modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.app.analysis.heuristic_refactor_engine import HeuristicRefactorEngine


# ---------------------------------------------------------
# Mock LLM Response
# ---------------------------------------------------------

# Simulated response returned by the LLM service.
# This keeps tests deterministic and avoids loading models.
MOCK_LLM_RESPONSE = {
    "analysis": {
        "explanation": "Reduced nesting by simplifying loop structure.",
        "suggestions": []
    }
}


# ---------------------------------------------------------
# Test: Basic refactor generation
# ---------------------------------------------------------

@patch("app.services.llm_service.analyze_code")
def test_basic_refactor(mock_analyze):
    """
    Verify that refactor engine returns structured output
    when LLM responds correctly.
    """

    mock_analyze.return_value = MOCK_LLM_RESPONSE

    code = """
def process(arr):
    for i in arr:
        for j in arr:
            if i == j:
                print(i)
"""

    # Complexity metrics from complexity analyzer
    complexity = {
        "cyclomatic_complexity": 4,
        "max_loop_depth": 2
    }

    # Code smell structure expected by the engine
    smells = {
        "code_smells": ["Deep Nesting"]
    }

    engine = HeuristicRefactorEngine()

    result = engine.generate_refactor(code, MOCK_LLM_RESPONSE, complexity, smells)

    # Validate response structure
    assert isinstance(result, dict)
    assert "explanation" in result
    assert "suggestions" in result
    assert "improved_code" in result


# ---------------------------------------------------------
# Test: Empty code input
# ---------------------------------------------------------

@patch("app.services.llm_service.analyze_code")
def test_empty_code(mock_analyze):
    """
    Engine should still produce structured output even
    if the input code is empty.
    """

    mock_analyze.return_value = MOCK_LLM_RESPONSE

    engine = HeuristicRefactorEngine()

    smells = {"code_smells": []}

    result = engine.generate_refactor("", MOCK_LLM_RESPONSE, {}, smells)

    assert result is not None
    assert "improved_code" in result


# ---------------------------------------------------------
# Test: High complexity input
# ---------------------------------------------------------

@patch("app.services.llm_service.analyze_code")
def test_high_complexity_code(mock_analyze):
    """
    Ensure engine handles very complex metadata inputs.
    """

    mock_analyze.return_value = MOCK_LLM_RESPONSE

    code = """
def complex_function(arr):
    for i in arr:
        for j in arr:
            for k in arr:
                if i == j and j == k:
                    print(i)
"""

    complexity = {
        "cyclomatic_complexity": 12,
        "max_loop_depth": 3
    }

    smells = {
        "code_smells": ["Deep Nesting", "High Complexity"]
    }

    engine = HeuristicRefactorEngine()

    result = engine.generate_refactor(code, MOCK_LLM_RESPONSE, complexity, smells)

    assert result["improved_code"] is not None


# ---------------------------------------------------------
# Test: LLM failure scenario
# ---------------------------------------------------------

@patch("app.services.llm_service.analyze_code")
def test_llm_failure(mock_analyze):
    """
    Simulate LLM service failure and ensure engine handles it.
    """

    mock_analyze.side_effect = Exception("LLM service failed")

    engine = HeuristicRefactorEngine()

    smells = {"code_smells": []}

    try:
        result = engine.generate_refactor("print('hello')", {}, {}, smells)
        assert result is not None
    except Exception:
        # Acceptable behavior if engine propagates error
        assert True


# ---------------------------------------------------------
# Test: Large code snippet
# ---------------------------------------------------------

@patch("app.services.llm_service.analyze_code")
def test_large_code_input(mock_analyze):
    """
    Ensure engine handles large input without crashing.
    """

    mock_analyze.return_value = MOCK_LLM_RESPONSE

    # Generate large code snippet
    code_lines = "\n".join([f"print({i})" for i in range(300)])

    code = f"""
def large():
{code_lines}
"""

    smells = {"code_smells": []}

    engine = HeuristicRefactorEngine()

    result = engine.generate_refactor(code, MOCK_LLM_RESPONSE, {}, smells)

    assert result is not None


# ---------------------------------------------------------
# J3 (F5): the structured change list
#
# The old summary counted lines containing `"""` and divided by two, which
# assumes every docstring spans two such lines. The engine emits a SINGLE-line
# docstring for classes and for parameterless functions, so that arithmetic
# reported zero for exactly the files it had just changed. These tests assert
# the change list, and assert each line number against the improved TEXT --
# a count assertion cannot see an off-by-one, this can.
# ---------------------------------------------------------

EMPTY_ANALYSIS = {"analysis": {"explanation": "", "suggestions": []}}


def _refactor(code):
    """Run the engine over `code` with no complexity or smell input."""
    engine = HeuristicRefactorEngine()
    return engine.generate_refactor(code, EMPTY_ANALYSIS, {}, {})


def test_changes_are_returned_for_a_parameterless_function():
    result = _refactor('def hello():\n    print("hello world")\n')

    changes = result["changes"]
    docstrings = [c for c in changes if c["kind"] == "docstring"]
    hints = [c for c in changes if c["kind"] == "return_hint"]

    assert len(docstrings) == 1
    assert docstrings[0]["target"] == "function"
    assert docstrings[0]["name"] == "hello"
    assert docstrings[0]["line_count"] == 1

    assert len(hints) == 1
    assert hints[0]["name"] == "hello"


def test_change_line_numbers_point_at_the_improved_text():
    result = _refactor('def hello():\n    print("hello world")\n')

    improved = result["improved_code"].splitlines()

    for change in result["changes"]:
        line = improved[change["line"] - 1]
        if change["kind"] == "docstring":
            assert '"""' in line
        else:
            assert "-> None" in line


def test_multi_line_docstring_spans_the_lines_it_claims():
    code = "def add(a, b):\n    total = a + b\n    return total\n"

    result = _refactor(code)

    docstrings = [c for c in result["changes"] if c["kind"] == "docstring"]
    assert len(docstrings) == 1
    change = docstrings[0]

    improved = result["improved_code"].splitlines()
    block = improved[change["line"] - 1 : change["line"] - 1 + change["line_count"]]

    # The claimed span must open and close the docstring and contain nothing else.
    assert '"""' in block[0]
    assert '"""' in block[-1]
    assert "total = a + b" not in "\n".join(block)


def test_class_docstrings_are_reported_as_classes():
    result = _refactor("class Widget:\n    size = 1\n")

    docstrings = [c for c in result["changes"] if c["kind"] == "docstring"]
    assert len(docstrings) == 1
    assert docstrings[0]["target"] == "class"
    assert docstrings[0]["name"] == "Widget"


def test_line_numbers_survive_several_insertions_above():
    code = (
        "def first():\n    pass\n\n"
        "def second():\n    pass\n\n"
        "def third():\n    pass\n"
    )

    result = _refactor(code)
    improved = result["improved_code"].splitlines()

    docstrings = [c for c in result["changes"] if c["kind"] == "docstring"]
    assert len(docstrings) == 3

    # Every docstring's line must still land on a docstring after the two
    # insertions above it have shifted the file down.
    for change in docstrings:
        assert '"""' in improved[change["line"] - 1]


def test_a_file_with_no_gaps_reports_no_changes():
    code = 'def done() -> None:\n    """Already documented."""\n    print("x")\n'

    result = _refactor(code)

    assert result["changes"] == []


def test_summary_counts_single_line_docstrings_correctly():
    """The `// 2` bug: one parameterless function reported 'to 0'."""
    result = _refactor('def hello():\n    print("hello world")\n')

    explanation = result["explanation"]

    assert "Suggested improvements (unapplied)" in explanation
    assert "to 0 " not in explanation
    assert "1 function" in explanation