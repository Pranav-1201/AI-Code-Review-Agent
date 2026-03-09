def compute_quality_score(issue_probability, complexity, security_issues):
    """
    Compute an overall code quality score between 0 and 100.
    Higher score means better code quality.
    """

    score = 100

    # Penalize if AI thinks issues are likely
    score -= int(issue_probability * 40)

    # Penalize complex algorithms
    if complexity == "O(n^2)":
        score -= 20
    elif complexity == "O(n^3)":
        score -= 30

    # Penalize security issues
    score -= 10 * len(security_issues)

    if score < 0:
        score = 0

    return score