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

from typing import List, Union, Dict, Tuple, Any


def compute_quality_score(
    issue_probability: float,
    complexity: Dict[str, Any],
    security_issues: List[Union[str, Dict]],
    is_test_file: bool = False
) -> Tuple[int, Dict[str, int]]:
    """
    Compute an overall code quality score.

    Parameters
    ----------
    issue_probability : float
        Probability that the model believes the code contains issues.

    complexity : Dict[str, Any]
        Estimated algorithmic complexity dict.

    security_issues : List[Union[str, Dict]]
        List of detected security issues (strings or dicts).

    is_test_file : bool
        If True, apply a lighter scoring model. Test files
        are excluded from health score computation and should
        not be penalized for assert usage.

    Returns
    -------
    Tuple[int, Dict[str, int]]
        (Score between 0 and 100, Breakdown Dictionary)
    """

    # ----------------------------------------------------------
    # Test file scoring: lighter model
    # Test files are excluded from health score aggregation,
    # but they still appear in the UI. Give them a reasonable
    # score that reflects code structure, not security penalties.
    # ----------------------------------------------------------

    if is_test_file:
        score = 100
        ai_pen = int(issue_probability * 15)
        score -= ai_pen  # Light AI penalty
        sec_pen = 0
        # Only penalize High/Critical security in test files
        for issue in security_issues:
            if isinstance(issue, dict):
                sev = issue.get("severity", "Medium").lower()
                if sev in ("critical", "high"):
                    sec_pen += 5
        
        score -= sec_pen
        final_score = max(75, min(score, 100))
        return (final_score, {"heuristics": -ai_pen, "security": -sec_pen, "complexity": 0})

    # ----------------------------------------------------------
    # Production file scoring: full model
    # ----------------------------------------------------------

    score = 100
    breakdown = {"heuristics": 0, "security": 0, "complexity": 0}

    # ------------------------------------------------------
    # Penalize if AI predicts issues
    # ------------------------------------------------------

    ai_pen = int(issue_probability * 20)
    score -= ai_pen
    breakdown["heuristics"] -= ai_pen

    # ------------------------------------------------------
    # Penalize based on complexity (Exponential mathematical drop)
    # ------------------------------------------------------

    cc = complexity.get("cyclomatic_complexity", 1)
    depth = complexity.get("max_loop_depth", 0)

    # Base penalty: CC exponential
    cc_pen = 0
    if cc > 3:
        cc_pen = int((cc - 3) ** 1.3)  # Gentle exponential scaling
    
    # Loop depth penalty
    if depth == 2:
        cc_pen += 5
    elif depth >= 3:
        cc_pen += 15
        
    cc_pen = min(cc_pen, 35) # Cap max complexity deduction at 35 points
    score -= cc_pen
    breakdown["complexity"] -= cc_pen

    # ------------------------------------------------------
    # Penalize security issues (severity-weighted)
    # ------------------------------------------------------

    severity_weights = {
        "critical": 12,
        "high": 8,
        "medium": 4,
        "low": 1,
        "info": 0
    }

    sec_pen = 0
    for issue in security_issues:
        if isinstance(issue, dict):
            sev = issue.get("severity", "High").lower()
            sec_pen += severity_weights.get(sev, 3)
        else:
            sec_pen += 3

    score -= sec_pen
    breakdown["security"] -= sec_pen

    # ------------------------------------------------------
    # Bonus for clean, small files with no issues
    # Small well-structured files deserve 95+ scores
    # ------------------------------------------------------

    if (len(security_issues) == 0
        and cc <= 5
        and depth <= 1
        and issue_probability < 0.6):
        if score < 95:
            bonus = min(95 - score, 15)  # Cap bonus
            score += bonus
            breakdown["heuristics"] += int(bonus * 0.5)
            breakdown["complexity"] += int(bonus * 0.5)

    # ------------------------------------------------------
    # Clamp score within valid range
    # ------------------------------------------------------

    final_score = max(0, min(score, 100))

    return (final_score, breakdown)