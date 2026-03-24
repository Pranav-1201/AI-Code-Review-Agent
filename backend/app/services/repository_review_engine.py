# ==========================================================
# File: repository_review_engine.py
# Purpose: Orchestrates repository-level AI code review
# ==========================================================

from typing import Dict, List

from app.services.repo_analyzer import analyze_repository
from app.services.llm_service import analyze_code
from app.services.report_generator import generate_review_report
from app.analysis.llm_refactor_engine import LLMRefactorEngine


# ----------------------------------------------------------
# Single File Analysis Worker
# ----------------------------------------------------------

def analyze_single_file(file_data: Dict, refactor_engine: LLMRefactorEngine) -> Dict:
    """
    Analyze a single repository file.
    """

    code = file_data["content"]
    file_name = file_data["file_name"]
    functions = file_data.get("functions", [])
    imports = file_data.get("imports", [])

    # ------------------------------------------------------
    # Extract analysis signals from repo analyzer
    # ------------------------------------------------------

    complexity_metrics = file_data.get("complexity_metrics", [])

    max_depth = 0
    for fn in complexity_metrics:
        max_depth = max(max_depth, fn.get("max_loop_depth", 0))

    complexity = {
        "max_loop_depth": max_depth
    }

    smells = file_data.get("code_smells", [])

    # ------------------------------------------------------
    # AI Code Analysis
    # ------------------------------------------------------

    analysis_result = analyze_code(
        code,
        functions=functions,
        imports=imports,
        complexity_metrics=complexity_metrics,   # ✅ NEW
        language="python"
    )

    analysis_section = analysis_result.get("analysis", {})

    # ------------------------------------------------------
    # Refactor Suggestions
    # ------------------------------------------------------

    refactor_result = refactor_engine.generate_refactor(
        code,
        analysis_result,
        complexity,
        smells
    )

    # ------------------------------------------------------
    # Generate Report
    # ------------------------------------------------------

    report = generate_review_report(
        file_name=file_name,
        analysis_result=analysis_result,
        refactor_result=refactor_result,
        complexity_metrics=complexity_metrics,
        smell_metrics=smells
    )

    score = analysis_result.get("code_quality_score", 0)
    issues = analysis_section.get("issues", [])
    security = analysis_section.get("security_risks", [])

    return {
        "report": report,
        "score": score,
        "issues_found": bool(issues),
        "security_count": len(security)
    }


# ==========================================================
# Repository Review Engine
# ==========================================================

class RepositoryReviewEngine:
    """
    Runs AI code review across an entire repository.
    """

    def __init__(self):
        self.refactor_engine = LLMRefactorEngine()

    def review_repository(self, repo_path: str) -> Dict:

        repo_data = analyze_repository(repo_path)

        file_reports: List[str] = []
        total_score = 0
        issue_files = 0
        security_issues = 0

        results = []

        # --------------------------------------------------
        # Sequential Processing (safe mode)
        # --------------------------------------------------

        for file_data in repo_data:
            result = analyze_single_file(file_data, self.refactor_engine)
            results.append(result)

        # --------------------------------------------------
        # Aggregate Results
        # --------------------------------------------------

        for result in results:

            file_reports.append(result["report"])

            total_score += result["score"]

            if result["issues_found"]:
                issue_files += 1

            security_issues += result["security_count"]

        file_count = len(results)

        avg_score = round(total_score / file_count, 2) if file_count else 0

        summary = {
            "files_analyzed": file_count,
            "files_with_issues": issue_files,
            "average_quality_score": avg_score,
            "total_security_issues": security_issues
        }

        return {
            "repository_summary": summary,
            "file_reports": file_reports
        }