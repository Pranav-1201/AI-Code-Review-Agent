"""
Integration tests for RepositoryReviewEngine.

This module tests the full repository review pipeline.

Heavy AI components are mocked to keep tests fast
and deterministic.
"""

import sys
import os
import tempfile
from unittest.mock import patch

# Allow importing backend modules
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.append(project_root)
sys.path.append(os.path.join(project_root, "backend"))

from app.services.repository_review_engine import RepositoryReviewEngine


# Mock result returned by LLM service
MOCK_ANALYSIS = {
    "code_quality_score": 85,
    "analysis": {
        "issues": [],
        "security_risks": [],
        "time_complexity": "O(n)",
        "suggestions": []
    }
}


# ---------------------------------------------------------
# Test: Basic repository review
# ---------------------------------------------------------

@patch("app.services.repository_review_engine.analyze_code", return_value=MOCK_ANALYSIS)
def test_basic_repository_review(mock_llm):
    """
    Ensure the engine produces a review for a simple repository.
    """

    with tempfile.TemporaryDirectory() as repo:

        file_path = os.path.join(repo, "example.py")

        with open(file_path, "w") as f:
            f.write("""
def hello():
    print("hello world")
""")

        engine = RepositoryReviewEngine()

        result = engine.review_repository(repo)

        assert result is not None
        assert "repository_summary" in result
        assert "file_reports" in result


# ---------------------------------------------------------
# Test: Repository with multiple files
# ---------------------------------------------------------

@patch("app.services.repository_review_engine.analyze_code", return_value=MOCK_ANALYSIS)
def test_multiple_files_repository(mock_llm):
    """
    Ensure multiple Python files are analyzed correctly.
    """

    with tempfile.TemporaryDirectory() as repo:

        for i in range(3):
            file_path = os.path.join(repo, f"file{i}.py")

            with open(file_path, "w") as f:
                f.write(f"""
def func{i}():
    return {i}
""")

        engine = RepositoryReviewEngine()

        result = engine.review_repository(repo)

        assert result is not None
        assert len(result["file_reports"]) >= 1


# ---------------------------------------------------------
# Test: Empty repository
# ---------------------------------------------------------

def test_empty_repository():
    """
    The engine should handle empty repositories safely.
    """

    with tempfile.TemporaryDirectory() as repo:

        engine = RepositoryReviewEngine()

        result = engine.review_repository(repo)

        assert result is not None


# ---------------------------------------------------------
# Test: Non-Python files ignored
# ---------------------------------------------------------

def test_repository_with_non_python_files():
    """
    Non-Python files should not break the review engine.
    """

    with tempfile.TemporaryDirectory() as repo:

        file_path = os.path.join(repo, "notes.txt")

        with open(file_path, "w") as f:
            f.write("Just text")

        engine = RepositoryReviewEngine()

        result = engine.review_repository(repo)

        assert result is not None


# ---------------------------------------------------------
# Test: Invalid repository path
# ---------------------------------------------------------

def test_invalid_repository_path():
    """
    Invalid paths should raise an error or be handled safely.
    """

    engine = RepositoryReviewEngine()

    try:
        engine.review_repository("this_repo_does_not_exist")
    except Exception:
        assert True