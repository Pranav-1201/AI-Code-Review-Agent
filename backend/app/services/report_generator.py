# ==========================================================
# File: report_generator.py
# Purpose: Convert AI analysis results into structured
#          reports and persist them in database + vector DB
# ==========================================================

from typing import Dict, Optional

from backend.database.review_repository import save_review
from rag.vector_store import ReviewVectorStore

# Rich terminal visualization
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box


console = Console()

# Lazy initialization of vector store
_vector_store = None


def get_vector_store():
    global _vector_store

    if _vector_store is None:
        _vector_store = ReviewVectorStore()

    return _vector_store


# ----------------------------------------------------------
# Main Report Generator
# ----------------------------------------------------------

def generate_review_report(
    file_name: str,
    analysis_result: Dict,
    refactor_result: Optional[Dict] = None,
    complexity_metrics=None,
    smell_metrics=None
) -> str:
    """
    Generate a readable AI review report and persist results.
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

    # ------------------------------------------------------
    # Structured database report
    # ------------------------------------------------------

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

# ------------------------------------------------------
# Prepare formatted sections (avoid backslashes in f-string)
# ------------------------------------------------------

    def _format_items(items):
        formatted = []

        for item in items:
            if isinstance(item, dict):
                formatted.append("- " + str(item.get("message", item)))
            else:
                formatted.append("- " + str(item))

        return "\n".join(formatted) if formatted else "None"


    issues_text = _format_items(issues) if issues else "None"
    security_text = _format_items(security) if security else "None"
    suggestions_text = _format_items(suggestions) if suggestions else "None"

    # ------------------------------------------------------
    # Rich Terminal Visualization
    # ------------------------------------------------------

    try:

        console.print(
            Panel.fit(
                "[bold cyan]AI CODE REVIEW REPORT[/bold cyan]",
                border_style="cyan"
            )
        )

        console.print(f"[bold]File:[/bold] {file_name}")

        # Metrics table
        table = Table(box=box.ROUNDED)

        table.add_column("Metric", style="bold")
        table.add_column("Value")

        table.add_row("Quality Score", f"{score}/100")
        table.add_row("Time Complexity", str(complexity))
        table.add_row("Issues Found", str(len(issues)))
        table.add_row("Security Risks", str(len(security)))

        console.print(table)

        if issues:
            console.print(
                Panel(
                    _format_items(issues),
                    title="Issues",
                    border_style="yellow"
                )
            )

        if security:
            console.print(
                Panel(
                    _format_items(security),
                    title="Security Risks",
                    border_style="red"
                )
            )

        if suggestions:
            console.print(
                Panel(
                    _format_items(suggestions),
                    title="Suggestions",
                    border_style="green"
                )
            )

    except Exception:
        # If Rich fails, silently fallback to normal behavior
        pass

    # ------------------------------------------------------
    # Human-readable report
    # ------------------------------------------------------

    report = f"""
================ AI CODE REVIEW REPORT ================

File: {file_name}

Quality Score: {score}/100

----------------------------------------
Issues
----------------------------------------
{issues_text}

----------------------------------------
Security Risks
----------------------------------------
{security_text}

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
{suggestions_text}

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

    # ------------------------------------------------------
    # Save review to database
    # ------------------------------------------------------

    try:

        review_id = save_review(
            repo_name="local_repo",
            commit_id="latest",
            score=score if isinstance(score, (int, float)) else 0,
            summary="Automated AI review",
            report=report_data
        )

# --------------------------------------------------
# Index summary in vector store for RAG retrieval
# --------------------------------------------------

# vector_summary = f"""
# File: {file_name}
# Score: {score}
# Issues: {issues}
# Suggestions: {suggestions}
# """

# get_vector_store().add_review(review_id, vector_summary)

    except Exception as e:
        print(f"Failed to store review: {e}")

    return report