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

from typing import List


def compute_quality_score(
    issue_probability: float,
    complexity: str,
    security_issues: List[str]
) -> int:
    """
    Compute an overall code quality score.

    Parameters
    ----------
    issue_probability : float
        Probability that the model believes the code contains issues.

    complexity : str
        Estimated algorithmic complexity.

    security_issues : List[str]
        List of detected security issues.

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
    # Penalize security issues
    # ------------------------------------------------------

    score -= 10 * len(security_issues)

    # ------------------------------------------------------
    # Clamp score within valid range
    # ------------------------------------------------------

    score = max(0, min(score, 100))

    return score