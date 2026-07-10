"""
Integration tests for RepositoryReviewEngine.

This module tests the full repository review pipeline.

Ported to the current API (Chunk 0):
  - review_repository(repo_path, repo_data) now takes the pre-computed
    repo_data from analyze_repository() (the same two-step the real
    pipeline in main.run_pipeline uses).
  - the analyze_code patch targets the module under its real import
    path (backend.app.services.repository_review_engine).
"""

import sys
import os
import tempfile
from unittest.mock import patch

# Allow importing backend modules
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.append(project_root)
sys.path.append(os.path.join(project_root, "backend"))

from backend.app.services.repository_review_engine import RepositoryReviewEngine
from backend.app.services.repo_analyzer import analyze_repository


# Mock result returned by the LLM/analysis service
MOCK_ANALYSIS = {
    "code_quality_score": 85,
    "breakdown": {},
    "analysis": {
        "issues": [],
        "security_risks": [],
        "time_complexity": "O(n)",
        "suggestions": [],
        "explanation": "",
    },
}

_PATCH_TARGET = "backend.app.services.repository_review_engine.analyze_code"


# ---------------------------------------------------------
# Test: Basic repository review
# ---------------------------------------------------------

@patch(_PATCH_TARGET, return_value=MOCK_ANALYSIS)
def test_basic_repository_review(mock_llm):
    """Ensure the engine produces a review for a simple repository."""

    with tempfile.TemporaryDirectory() as repo:
        with open(os.path.join(repo, "example.py"), "w") as f:
            f.write('def hello():\n    print("hello world")\n')

        engine = RepositoryReviewEngine()
        repo_data = analyze_repository(repo)
        result = engine.review_repository(repo, repo_data)

        assert result is not None
        assert "repository_summary" in result
        assert "file_reports" in result


# ---------------------------------------------------------
# Test: Repository with multiple files
# ---------------------------------------------------------

@patch(_PATCH_TARGET, return_value=MOCK_ANALYSIS)
def test_multiple_files_repository(mock_llm):
    """Ensure multiple Python files are analyzed correctly."""

    with tempfile.TemporaryDirectory() as repo:
        for i in range(3):
            with open(os.path.join(repo, f"file{i}.py"), "w") as f:
                f.write(f"def func{i}():\n    return {i}\n")

        engine = RepositoryReviewEngine()
        repo_data = analyze_repository(repo)
        result = engine.review_repository(repo, repo_data)

        assert result is not None
        assert len(result["file_reports"]) >= 3
        assert result["repository_summary"]["production_files"] >= 3


# ---------------------------------------------------------
# Test: Empty repository
# ---------------------------------------------------------

def test_empty_repository():
    """The engine should handle empty repositories safely."""

    with tempfile.TemporaryDirectory() as repo:
        engine = RepositoryReviewEngine()
        result = engine.review_repository(repo, analyze_repository(repo))

        assert result is not None
        assert result["file_reports"] == []


# ---------------------------------------------------------
# Test: Non-Python files ignored
# ---------------------------------------------------------

def test_repository_with_non_python_files():
    """Non-Python files should not break the review engine."""

    with tempfile.TemporaryDirectory() as repo:
        with open(os.path.join(repo, "notes.txt"), "w") as f:
            f.write("Just text")

        engine = RepositoryReviewEngine()
        result = engine.review_repository(repo, analyze_repository(repo))

        assert result is not None


# ---------------------------------------------------------
# Test: Invalid repository path
# ---------------------------------------------------------

def test_invalid_repository_path():
    """Invalid paths should be handled safely (empty analysis, no crash)."""

    engine = RepositoryReviewEngine()
    # analyze_repository walks a non-existent path -> yields nothing
    result = engine.review_repository("this_repo_does_not_exist",
                                      analyze_repository("this_repo_does_not_exist"))
    assert result is not None
    assert result["file_reports"] == []
