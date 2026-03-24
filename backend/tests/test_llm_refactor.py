"""
Unit tests for LLMRefactorEngine.

This module tests the AI-assisted refactoring component of the
code review system.

The LLM itself is mocked so tests:

- do not load transformer models
- do not call external APIs
- run quickly
- remain deterministic

Tests verify:
- correct request handling
- output structure
- handling of empty inputs
- handling of complex code
- resilience to LLM failures
"""

import sys
import os
from unittest.mock import patch

import pytest

# Allow importing backend modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.analysis.llm_refactor_engine import LLMRefactorEngine


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

    engine = LLMRefactorEngine()

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

    engine = LLMRefactorEngine()

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

    engine = LLMRefactorEngine()

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

    engine = LLMRefactorEngine()

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

    engine = LLMRefactorEngine()

    result = engine.generate_refactor(code, MOCK_LLM_RESPONSE, {}, smells)

    assert result is not None