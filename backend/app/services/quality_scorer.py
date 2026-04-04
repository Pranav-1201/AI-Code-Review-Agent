# ==========================================================
# File: quality_scorer.py
# Location: backend/app/services
#
# Purpose
# ----------------------------------------------------------
# Computes an overall code quality score between 0 and 100
# based on signals from:
#
# • AI issue probability
# • estimated algorithmic complexity
# • detected security issues
#
# Higher score = better code quality.
#
# Scoring modes:
#   - Production files: full penalty model
#   - Test files: neutral baseline (excluded from health score
#     aggregation anyway, but displayed in UI)
#   - Non-code files: default 100 (not processed)
# ==========================================================

from typing import List, Union, Dict


def compute_quality_score(
    issue_probability: float,
    complexity: str,
    security_issues: List[Union[str, Dict]],
    is_test_file: bool = False
) -> int:
    """
    Compute an overall code quality score.

    Parameters
    ----------
    issue_probability : float
        Probability that the model believes the code contains issues.

    complexity : str
        Estimated algorithmic complexity.

    security_issues : List[Union[str, Dict]]
        List of detected security issues (strings or dicts).

    is_test_file : bool
        If True, apply a lighter scoring model. Test files
        are excluded from health score computation and should
        not be penalized for assert usage.

    Returns
    -------
    int
        Score between 0 and 100.
    """

    # ----------------------------------------------------------
    # Test file scoring: lighter model
    # Test files are excluded from health score aggregation,
    # but they still appear in the UI. Give them a reasonable
    # score that reflects code structure, not security penalties.
    # ----------------------------------------------------------

    if is_test_file:
        score = 100
        score -= int(issue_probability * 15)  # Light AI penalty
        # Only penalize High/Critical security in test files
        for issue in security_issues:
            if isinstance(issue, dict):
                sev = issue.get("severity", "Medium").lower()
                if sev in ("critical", "high"):
                    score -= 5
        return max(75, min(score, 100))

    # ----------------------------------------------------------
    # Production file scoring: full model
    # ----------------------------------------------------------

    score = 100

    # ------------------------------------------------------
    # Penalize if AI predicts issues
    # ------------------------------------------------------

    score -= int(issue_probability * 40)

    # ------------------------------------------------------
    # Penalize based on complexity
    # ------------------------------------------------------

    complexity_penalties = {
        "O(n²)": 15,
        "O(n^2)": 15,
        "O(n³)": 25,
        "O(n^3)": 25,
        "O(n^k)": 30
    }

    score -= complexity_penalties.get(complexity, 0)

    # ------------------------------------------------------
    # Penalize security issues (severity-weighted)
    # Less aggressive than before — Critical was 15, now 12
    # to avoid over-penalizing framework code that has
    # legitimate eval/exec usage.
    # ------------------------------------------------------

    severity_weights = {
        "critical": 12,
        "high": 8,
        "medium": 4,
        "low": 1
    }

    for issue in security_issues:
        if isinstance(issue, dict):
            sev = issue.get("severity", "High").lower()
            score -= severity_weights.get(sev, 5)
        else:
            score -= 5

    # ------------------------------------------------------
    # Clamp score within valid range
    # ------------------------------------------------------

    score = max(0, min(score, 100))

    return score