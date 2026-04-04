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
    # Reduced from 40 to 20 — CodeBERT regularly outputs
    # 0.45-0.55 for perfectly clean files, which was capping
    # scores at ~80 even for excellent code.
    # ------------------------------------------------------

    score -= int(issue_probability * 20)

    # ------------------------------------------------------
    # Penalize based on complexity
    # Reduced penalties — O(n²) is common in frameworks
    # and shouldn't crater the score by itself.
    # ------------------------------------------------------

    complexity_penalties = {
        "O(n²)": 10,
        "O(n^2)": 10,
        "O(n³)": 18,
        "O(n^3)": 18,
        "O(n^k)": 22
    }

    score -= complexity_penalties.get(complexity, 0)

    # ------------------------------------------------------
    # Penalize security issues (severity-weighted)
    # Info-level issues get 0 penalty (informational only)
    # ------------------------------------------------------

    severity_weights = {
        "critical": 12,
        "high": 8,
        "medium": 4,
        "low": 1,
        "info": 0
    }

    for issue in security_issues:
        if isinstance(issue, dict):
            sev = issue.get("severity", "High").lower()
            score -= severity_weights.get(sev, 3)
        else:
            score -= 3

    # ------------------------------------------------------
    # Bonus for clean, small files with no issues
    # Small well-structured files deserve 95+ scores
    # ------------------------------------------------------

    if (len(security_issues) == 0
        and complexity in ("O(1)", "O(n)")
        and issue_probability < 0.6):
        score = max(score, 88)  # Floor for clean files

    # ------------------------------------------------------
    # Clamp score within valid range
    # ------------------------------------------------------

    score = max(0, min(score, 100))

    return score