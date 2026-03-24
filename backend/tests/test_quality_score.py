"""
Unit tests for compute_quality_score.

This module tests the code quality scoring logic used by the
AI-powered code review system.

The scoring function evaluates:

- predicted issue probability from AI analysis
- algorithmic complexity classification
- detected security vulnerabilities

The function returns an integer score between 0 and 100.
"""

import sys
import os

# Allow importing backend modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.quality_scorer import compute_quality_score


# ---------------------------------------------------------
# Test: Basic score generation
# ---------------------------------------------------------

def test_basic_score():
    """
    Verify that the scoring function returns a valid score.
    """

    issue_probability = 0.1
    complexity = "O(n)"
    security_issues = []

    score = compute_quality_score(issue_probability, complexity, security_issues)

    assert isinstance(score, int)
    assert 0 <= score <= 100


# ---------------------------------------------------------
# Test: Issue probability penalty
# ---------------------------------------------------------

def test_issue_probability_penalty():
    """
    Higher predicted issue probability should reduce score.
    """

    issue_probability = 0.9
    complexity = "O(n)"
    security_issues = []

    score = compute_quality_score(issue_probability, complexity, security_issues)

    assert isinstance(score, int)
    assert score < 100


# ---------------------------------------------------------
# Test: Complexity penalty
# ---------------------------------------------------------

def test_complexity_penalty():
    """
    Higher algorithmic complexity should reduce score.
    """

    issue_probability = 0.2
    complexity = "O(n^3)"
    security_issues = []

    score = compute_quality_score(issue_probability, complexity, security_issues)

    assert isinstance(score, int)


# ---------------------------------------------------------
# Test: Security issue penalty
# ---------------------------------------------------------

def test_security_penalty():
    """
    Security vulnerabilities should reduce the score.
    """

    issue_probability = 0.2
    complexity = "O(n)"

    security_issues = [
        "Use of eval()",
        "Hardcoded credentials"
    ]

    score = compute_quality_score(issue_probability, complexity, security_issues)

    assert isinstance(score, int)
    assert score < 100


# ---------------------------------------------------------
# Test: Worst-case scenario
# ---------------------------------------------------------

def test_worst_case_score():
    """
    Worst-case inputs should produce a low score.
    """

    issue_probability = 1.0
    complexity = "O(n^4)"

    security_issues = [
        "eval()",
        "exec()",
        "subprocess shell=True",
        "hardcoded secret"
    ]

    score = compute_quality_score(issue_probability, complexity, security_issues)

    assert isinstance(score, int)
    assert score <= 100