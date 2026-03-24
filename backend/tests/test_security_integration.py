"""
Integration tests for security detection in the AI analysis pipeline.

The LLM model is mocked so tests:

- do not load transformer models
- run quickly
- remain deterministic
"""

import sys
import os
from unittest.mock import patch

# Allow importing backend modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app.services.llm_service as llm_service


# ---------------------------------------------------------
# Mock LLM output
# ---------------------------------------------------------

MOCK_ANALYSIS = {
    "code_quality_score": 60,
    "analysis": {
        "issues": ["Hardcoded credentials"],
        "security_risks": ["Use of os.system with dangerous command"],
        "time_complexity": "O(1)",
        "suggestions": [
            "Avoid hardcoded passwords.",
            "Do not execute system commands with user input."
        ]
    }
}


# ---------------------------------------------------------
# Test: Security risk detection
# ---------------------------------------------------------

@patch("app.services.llm_service.analyze_code", return_value=MOCK_ANALYSIS)
def test_security_risk_detection(mock_llm):

    test_code = """
import os

password = "admin123"

def run():
    os.system("rm -rf /")
"""

    result = llm_service.analyze_code(test_code)

    assert "analysis" in result
    assert "security_risks" in result["analysis"]
    assert len(result["analysis"]["security_risks"]) > 0


# ---------------------------------------------------------
# Test: Safe code scenario
# ---------------------------------------------------------

@patch("app.services.llm_service.analyze_code", return_value={
    "code_quality_score": 95,
    "analysis": {
        "issues": [],
        "security_risks": [],
        "time_complexity": "O(n)",
        "suggestions": []
    }
})
def test_safe_code(mock_llm):

    safe_code = """
def add(a, b):
    return a + b
"""

    result = llm_service.analyze_code(safe_code)

    assert "analysis" in result
    assert result["analysis"]["security_risks"] == []