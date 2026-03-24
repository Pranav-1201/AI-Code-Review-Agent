"""
Unit tests for RefactoringEngine.

This module tests the rule-based refactoring suggestion engine used
in the AI code review system.

The refactoring engine generates improvement suggestions based on:

- complexity metrics
- detected code smells

These tests ensure that:

- suggestions are generated when complexity is high
- suggestions are generated for code smells
- multiple issues generate multiple suggestions
- the engine handles empty inputs safely
"""

import sys
import os

# Allow importing backend modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.analysis.refactoring_engine import RefactoringEngine


# ---------------------------------------------------------
# Test: Suggestions generated for high complexity
# ---------------------------------------------------------

def test_high_complexity_suggestions():
    """
    High cyclomatic complexity and loop depth should produce suggestions.
    """

    complexity = {
        "cyclomatic_complexity": 12,
        "max_loop_depth": 3,
        "recursive": False
    }

    smells = {"code_smells": []}

    engine = RefactoringEngine()

    suggestions = engine.generate_suggestions(complexity, smells)

    assert isinstance(suggestions, list)
    assert len(suggestions) > 0


# ---------------------------------------------------------
# Test: Suggestions generated for code smells
# ---------------------------------------------------------

def test_code_smell_suggestions():
    """
    Code smells should produce refactoring suggestions.
    """

    complexity = {}

    smells = {
        "code_smells": ["Deep Nesting", "Magic Numbers"]
    }

    engine = RefactoringEngine()

    suggestions = engine.generate_suggestions(complexity, smells)

    assert isinstance(suggestions, list)
    assert len(suggestions) >= 1


# ---------------------------------------------------------
# Test: Multiple issues generate multiple suggestions
# ---------------------------------------------------------

def test_multiple_issues():
    """
    When both complexity and smells exist, multiple suggestions
    should be produced.
    """

    complexity = {
        "cyclomatic_complexity": 15,
        "max_loop_depth": 4,
        "recursive": True
    }

    smells = {
        "code_smells": [
            "Deep Nesting",
            "Magic Numbers",
            "Long Function"
        ]
    }

    engine = RefactoringEngine()

    suggestions = engine.generate_suggestions(complexity, smells)

    assert isinstance(suggestions, list)
    assert len(suggestions) >= 2


# ---------------------------------------------------------
# Test: No issues present
# ---------------------------------------------------------

def test_no_issues():
    """
    If complexity is low and no smells exist,
    suggestions should be empty or minimal.
    """

    complexity = {
        "cyclomatic_complexity": 1,
        "max_loop_depth": 0,
        "recursive": False
    }

    smells = {"code_smells": []}

    engine = RefactoringEngine()

    suggestions = engine.generate_suggestions(complexity, smells)

    assert isinstance(suggestions, list)


# ---------------------------------------------------------
# Test: Empty input safety
# ---------------------------------------------------------

def test_empty_inputs():
    """
    Engine should handle empty dictionaries safely.
    """

    engine = RefactoringEngine()

    suggestions = engine.generate_suggestions({}, {})

    assert isinstance(suggestions, list)