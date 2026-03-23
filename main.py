import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), "backend"))
from app.analysis import call_graph
from backend.app.services.repo_analyzer import analyze_repository
from backend.app.services.llm_service import analyze_code
from backend.app.services.report_generator import generate_review_report

def run_pipeline(repo_path):

    print("Starting repository analysis...\n")

    files = analyze_repository(repo_path)

    from app.analysis.dependency_graph import build_dependency_graph
    from app.analysis.call_graph import build_call_graph

    dependency_graph = build_dependency_graph(files)
    print("Dependency Graph:", dependency_graph)

    call_graph = build_call_graph(files)
    print("Call Graph:", dict(call_graph))

    for file in files:

        # If repo_analyzer returns just code strings
        if isinstance(file, str):
            file_name = "unknown_file"
            code = file
            functions = []
            imports = []

        # If repo_analyzer returns dicts
        else:
            file_name = file.get("file_name", "unknown_file")
            code = file.get("content", "")
            functions = file.get("functions", [])
            imports = file.get("imports", [])

        print(f"Analyzing {file_name}...")

        analysis_result = analyze_code(code, functions, imports)

        report = generate_review_report(file_name, analysis_result)

        print(report)
        print("-" * 50)

        print("Functions:", functions)
        print("Imports:", imports)

        


if __name__ == "__main__":

    repo_path = "rag/data"

    run_pipeline(repo_path)