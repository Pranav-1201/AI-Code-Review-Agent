import os
from app.services.llm_service import analyze_code
from app.services.report_generator import generate_review_report

SUPPORTED_EXTENSIONS = (".py", ".cpp", ".js", ".java")


def analyze_repository(repo_path: str):
    """
    Analyze all supported code files in a repository.
    """

    results = []

    for root, dirs, files in os.walk(repo_path):

        for file in files:

            if file.endswith(SUPPORTED_EXTENSIONS):

                path = os.path.join(root, file)

                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    code = f.read()

                analysis = analyze_code(code)

                report = generate_review_report(file, analysis)

                results.append({
                    "file": path,
                    "analysis": analysis,
                    "report": report
                })

    return {
        "total_files_analyzed": len(results),
        "files": results
    }