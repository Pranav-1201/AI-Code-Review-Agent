# ==========================================================
# File: main.py
# Purpose: Entry point for AI repository code review
# ==========================================================

import sys
import os

project_root = os.path.abspath(os.path.dirname(__file__))
sys.path.append(os.path.join(project_root, "backend"))

from app.services.repo_analyzer import analyze_repository
from app.analysis.dependency_graph import build_dependency_graph
from app.analysis.call_graph import build_call_graph
from app.services.llm_service import analyze_code
from app.services.report_generator import generate_review_report


def run_pipeline(repo_path: str):

    print("Starting repository analysis...\n")

    # ------------------------------------------------------
    # Repository scanning
    # ------------------------------------------------------

    files = analyze_repository(repo_path)

    # ------------------------------------------------------
    # Dependency Graph
    # ------------------------------------------------------

    dependency_graph = build_dependency_graph(files)
    print("Dependency Graph:", dependency_graph)

    # ------------------------------------------------------
    # Call Graph
    # ------------------------------------------------------

    call_graph = build_call_graph(files)
    print("Call Graph:", dict(call_graph))

    # ------------------------------------------------------
    # Analyze each file
    # ------------------------------------------------------

    for file in files:

        file_name = file.get("file_name", "unknown_file")
        code = file.get("content", "")
        functions = file.get("functions", [])
        imports = file.get("imports", [])

        print(f"\nAnalyzing {file_name}...")

        analysis_result = analyze_code(
            code,
            functions=functions,
            imports=imports
        )

        report = generate_review_report(
            file_name,
            analysis_result
        )

        print(report)
        print("-" * 60)

        print("Functions:", functions)
        print("Imports:", imports)


# ----------------------------------------------------------
# Script Entry Point
# ----------------------------------------------------------

import sys

if __name__ == "__main__":

    if len(sys.argv) > 1:
        repo_path = sys.argv[1]
    else:
        repo_path = "rag/data"

    run_pipeline(repo_path)