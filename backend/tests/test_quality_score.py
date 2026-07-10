"""
Unit tests for compute_quality_score.

Ported to the current API (Chunk 0):
  - `complexity` is now a dict of AST-derived signals
    ({"cyclomatic_complexity": int, "max_loop_depth": int}),
    not a legacy time-complexity string.
  - the function returns a (score, breakdown) tuple, not a bare int.

The scoring function evaluates predicted issue probability,
algorithmic complexity, and detected security vulnerabilities,
and returns a score between 0 and 100 plus a penalty breakdown.
"""

import sys
import os

# Allow importing backend modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.app.services.quality_scorer import compute_quality_score


# Representative complexity dicts (replace the old "O(...)" strings)
CX_O1 = {"cyclomatic_complexity": 1, "max_loop_depth": 0}
CX_ON = {"cyclomatic_complexity": 2, "max_loop_depth": 1}
CX_ON3 = {"cyclomatic_complexity": 20, "max_loop_depth": 3}
CX_ON4 = {"cyclomatic_complexity": 30, "max_loop_depth": 4}


# ---------------------------------------------------------
# Test: Basic score generation
# ---------------------------------------------------------

def test_basic_score():
    """Verify that the scoring function returns a valid score."""

    score, breakdown = compute_quality_score(0.1, CX_ON, [])

    assert isinstance(score, int)
    assert isinstance(breakdown, dict)
    assert 0 <= score <= 100


# ---------------------------------------------------------
# Test: Issue probability penalty
# ---------------------------------------------------------

def test_issue_probability_penalty():
    """Higher predicted issue probability should reduce score."""

    score, _ = compute_quality_score(0.9, CX_ON, [])

    assert isinstance(score, int)
    assert score < 100


# ---------------------------------------------------------
# Test: Complexity penalty
# ---------------------------------------------------------

def test_complexity_penalty():
    """Higher algorithmic complexity should reduce score."""

    low, _ = compute_quality_score(0.2, CX_O1, [])
    high, _ = compute_quality_score(0.2, CX_ON3, [])

    assert isinstance(high, int)
    # A deeply nested, high-CC file must score below a trivial one.
    assert high < low


# ---------------------------------------------------------
# Test: Security issue penalty
# ---------------------------------------------------------

def test_security_penalty():
    """Security vulnerabilities should reduce the score."""

    security_issues = [
        "Use of eval()",
        "Hardcoded credentials",
    ]

    score, _ = compute_quality_score(0.2, CX_ON, security_issues)

    assert isinstance(score, int)
    assert score < 100


# ---------------------------------------------------------
# Test: Worst-case scenario
# ---------------------------------------------------------

def test_worst_case_score():
    """Worst-case inputs should produce a low score."""

    security_issues = [
        {"severity": "Critical", "type": "Dangerous Function"},
        {"severity": "Critical", "type": "Dangerous Function"},
        {"severity": "High", "type": "Command Injection"},
        {"severity": "High", "type": "Hardcoded Credential"},
    ]

    score, _ = compute_quality_score(1.0, CX_ON4, security_issues)

    assert isinstance(score, int)
    assert 0 <= score <= 100
    # Worst-case must land well below a clean baseline.
    clean, _ = compute_quality_score(0.0, CX_O1, [])
    assert score < clean
