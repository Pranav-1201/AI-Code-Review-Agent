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
# ==========================================================

from typing import List, Union, Dict


def compute_quality_score(
    issue_probability: float,
    complexity: str,
    security_issues: List[Union[str, Dict]]
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

    Returns
    -------
    int
        Score between 0 and 100.
    """

    score = 100

    # ------------------------------------------------------
    # Penalize if AI predicts issues
    # ------------------------------------------------------

    score -= int(issue_probability * 40)

    # ------------------------------------------------------
    # Penalize based on complexity
    # ------------------------------------------------------

    complexity_penalties = {
        "O(n^2)": 20,
        "O(n^3)": 30,
        "O(n^k)": 35
    }

    score -= complexity_penalties.get(complexity, 0)

    # ------------------------------------------------------
    # Penalize security issues (severity-weighted)
    # ------------------------------------------------------

    severity_weights = {
        "critical": 15,
        "high": 10,
        "medium": 5,
        "low": 2
    }

    for issue in security_issues:
        if isinstance(issue, dict):
            sev = issue.get("severity", "High").lower()
            score -= severity_weights.get(sev, 10)
        else:
            score -= 10

    # ------------------------------------------------------
    # Clamp score within valid range
    # ------------------------------------------------------

    score = max(0, min(score, 100))

    return score