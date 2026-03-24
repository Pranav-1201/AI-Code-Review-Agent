from database.review_repository import save_review
from rag.vector_store import ReviewVectorStore

# Initialize vector store
vector_store = ReviewVectorStore()


def generate_review_report(file_name, analysis_result, refactor_result=None, complexity_metrics=None, smell_metrics=None):
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

    explanation = ""
    improved_code = ""
    patch = ""

    if refactor_result:
        explanation = refactor_result.get("explanation", "")
        improved_code = refactor_result.get("improved_code", "")
        patch = refactor_result.get("patch", "")

    # -------- Structured data for database --------
    report_data = {
        "file_name": file_name,
        "score": score,
        "issues": issues,
        "security_risks": security,
        "complexity": complexity,
        "suggestions": suggestions,
        "complexity_metrics": complexity_metrics,
        "code_smells": smell_metrics,
        "ai_explanation": explanation,
        "improved_code": improved_code,
        "patch": patch
    }

    # -------- Human-readable report --------
    report = f"""
================ AI CODE REVIEW REPORT ================

File: {file_name}

Quality Score: {score}/100

----------------------------------------
Issues
----------------------------------------
{chr(10).join("- " + i for i in issues) if issues else "None"}

----------------------------------------
Security Risks
----------------------------------------
{chr(10).join("- " + s for s in security) if security else "None"}

----------------------------------------
Estimated Time Complexity
----------------------------------------
{complexity}

----------------------------------------
Code Smells
----------------------------------------
{smell_metrics if smell_metrics else "None"}

----------------------------------------
AI Explanation
----------------------------------------
{explanation if explanation else "N/A"}

----------------------------------------
Suggestions
----------------------------------------
{chr(10).join("- " + s for s in suggestions) if suggestions else "None"}

----------------------------------------
Improved Code
----------------------------------------
{improved_code if improved_code else "N/A"}

----------------------------------------
Patch
----------------------------------------
{patch if patch else "N/A"}

=======================================================
"""

    # Save review in database
    try:
        review_id = save_review(
            repo_name="local_repo",
            commit_id="latest",
            score=score if isinstance(score, (int, float)) else 0,
            summary="Automated AI review",
            report=report_data
        )

        # Index review in vector store for RAG retrieval
        vector_store.add_review(review_id, report)

    except Exception as e:
        print("Database save failed:", e)

    return report