import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), "backend"))
from backend.app.services.repo_analyzer import analyze_repository
from backend.app.services.llm_service import analyze_code
from backend.app.services.report_generator import generate_review_report


def run_pipeline(repo_path):

    print("Starting repository analysis...\n")

    files = analyze_repository(repo_path)

    for file in files:

        # If repo_analyzer returns just code strings
        if isinstance(file, str):
            file_name = "unknown_file"
            code = file

        # If repo_analyzer returns dicts
        else:
            file_name = file.get("file_name", "unknown_file")
            code = file.get("content", "")

        print(f"Analyzing {file_name}...")

        analysis_result = analyze_code(code)

        report = generate_review_report(file_name, analysis_result)

        print(report)
        print("-" * 50)

        


if __name__ == "__main__":

    repo_path = "rag/data"

    run_pipeline(repo_path)