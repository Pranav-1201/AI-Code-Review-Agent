def generate_review_report(file_name, analysis_result):
    """
    Convert AI analysis output into a readable review report.
    """

    score = analysis_result.get("code_quality_score", "N/A")
    analysis = analysis_result.get("analysis", {})

    issues = analysis.get("issues", [])
    security = analysis.get("security_risks", [])
    complexity = analysis.get("time_complexity", "Unknown")
    suggestions = analysis.get("suggestions", [])

    report = f"""
FILE: {file_name}

Code Quality Score: {score} / 100

Issues:
{chr(10).join("- " + i for i in issues)}

Security Risks:
{chr(10).join("- " + s for s in security)}

Time Complexity:
{complexity}

Suggestions:
{chr(10).join("- " + s for s in suggestions)}
"""

    return report
