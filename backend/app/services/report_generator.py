from backend.database.review_repository import save_review


def generate_review_report(file_name, analysis_result):
    """
    Convert AI analysis output into a readable review report
    and store the structured review in the database.
    """

    score = analysis_result.get("code_quality_score", "N/A")
    analysis = analysis_result.get("analysis", {})

    issues = analysis.get("issues", [])
    security = analysis.get("security_risks", [])
    complexity = analysis.get("time_complexity", "Unknown")
    suggestions = analysis.get("suggestions", [])

    # -------- Structured data for database --------
    report_data = {
        "file_name": file_name,
        "score": score,
        "issues": issues,
        "security_risks": security,
        "complexity": complexity,
        "suggestions": suggestions
    }

    # Save review in database
    try:
        save_review(
            repo_name="local_repo",
            commit_id="latest",
            score=score if isinstance(score, (int, float)) else 0,
            summary="Automated AI review",
            report=report_data
        )
    except Exception as e:
        print("Database save failed:", e)

    # -------- Human-readable report --------
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