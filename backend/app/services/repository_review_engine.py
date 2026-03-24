import os

from app.services.repo_analyzer import analyze_repository
from app.services.llm_service import analyze_code
from app.services.report_generator import generate_review_report
from app.analysis.llm_refactor_engine import LLMRefactorEngine


class RepositoryReviewEngine:

    def __init__(self):
        self.refactor_engine = LLMRefactorEngine()

    def review_repository(self, repo_path):
        """
        Perform AI code review on an entire repository.
        """

        repo_data = analyze_repository(repo_path)

        file_reports = []
        total_score = 0
        issue_files = 0
        security_issues = 0

        for file_data in repo_data:

            code = file_data["content"]
            file_name = file_data["file_name"]
            functions = file_data.get("functions", [])
            imports = file_data.get("imports", [])

            # Run AI analysis
            analysis_result = analyze_code(
                code,
                functions=functions,
                imports=imports,
                language="python"
            )

            # Run refactor engine
            refactor_result = self.refactor_engine.generate_refactor(
                code,
                complexity={"max_loop_depth": 2},
                smells=[]
            )

            # Generate review report
            report = generate_review_report(
                file_name=file_name,
                analysis_result=analysis_result,
                refactor_result=refactor_result
            )

            file_reports.append(report)

            score = analysis_result.get("code_quality_score", 0)
            total_score += score

            if analysis_result["analysis"]["issues"]:
                issue_files += 1

            security_issues += len(
                analysis_result["analysis"].get("security_risks", [])
            )

        file_count = len(file_reports)

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