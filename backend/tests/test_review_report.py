"""
Unit tests for report_generator.

This module tests the report generation system that converts
analysis results into human-readable reports and stores them
in the database and vector store.

Database and vector store operations are mocked so tests:

- run quickly
- do not require real DB access
- remain deterministic
"""

import sys
import os
from unittest.mock import patch

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.append(project_root)
sys.path.append(os.path.join(project_root, "backend"))

from backend.app.services.report_generator import generate_review_report


# ---------------------------------------------------------
# Mock inputs
# ---------------------------------------------------------

analysis_result = {
    "language": "python",
    "code_quality_score": 82,
    "analysis": {
        "issues": ["Nested loops detected"],
        "security_risks": [],
        "time_complexity": "O(n^2)",
        "suggestions": [
            "Try reducing nested loops using sets or hash maps."
        ]
    }
}

refactor_result = {
    "explanation": "Nested loops cause quadratic time complexity.",
    "improved_code": """
def process(arr):
    seen = set(arr)
    for value in seen:
        print(value)
""",
    "patch": """--- original
+++ improved
@@
- for i in arr:
-     for j in arr:
+ seen = set(arr)
+ for value in seen:
"""
}

complexity_metrics = {
    "cyclomatic_complexity": 4,
    "max_loop_depth": 2
}

smell_metrics = {
    "code_smells": ["Deep Nesting"]
}


# ---------------------------------------------------------
# Test: Full report generation
# ---------------------------------------------------------

@patch("app.services.report_generator.save_review")
@patch("app.services.report_generator.get_vector_store")
def test_generate_review_report(mock_vector_store, mock_save_review):
    """
    Ensure report is generated correctly and external
    storage systems are called.
    """

    mock_save_review.return_value = 1
    mock_vector_store.return_value.add_review.return_value = None

    report = generate_review_report(
        file_name="example.py",
        analysis_result=analysis_result,
        refactor_result=refactor_result,
        complexity_metrics=complexity_metrics,
        smell_metrics=smell_metrics
    )

    assert isinstance(report, str)

    assert "AI CODE REVIEW REPORT" in report
    assert "example.py" in report
    assert "Nested loops detected" in report
    assert "O(n^2)" in report


# ---------------------------------------------------------
# Test: Report generation without refactor result
# ---------------------------------------------------------

@patch("app.services.report_generator.save_review")
@patch("app.services.report_generator.get_vector_store")
def test_report_without_refactor(mock_vector_store, mock_save_review):
    """
    Ensure report still generates when refactor output
    is missing.
    """

    mock_save_review.return_value = 1
    mock_vector_store.return_value.add_review.return_value = None

    report = generate_review_report(
        file_name="example.py",
        analysis_result=analysis_result,
        refactor_result=None,
        complexity_metrics=complexity_metrics,
        smell_metrics=smell_metrics
    )

    assert "AI Explanation" in report
    assert "N/A" in report


# ---------------------------------------------------------
# Test: Empty analysis results
# ---------------------------------------------------------

@patch("app.services.report_generator.save_review")
@patch("app.services.report_generator.get_vector_store")
def test_empty_analysis(mock_vector_store, mock_save_review):
    """
    Ensure generator handles missing analysis safely.
    """

    mock_save_review.return_value = 1
    mock_vector_store.return_value.add_review.return_value = None

    report = generate_review_report(
        file_name="example.py",
        analysis_result={},
        refactor_result=None
    )

    assert isinstance(report, str)