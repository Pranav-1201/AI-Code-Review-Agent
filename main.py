# ==========================================================
# File: main.py
# Purpose: Entry point for AI repository code review
# ==========================================================

import sys
import os

# ----------------------------------------------------------
# Ensure backend is on Python path
# ----------------------------------------------------------

project_root = os.path.abspath(os.path.dirname(__file__))
sys.path.append(os.path.join(project_root, "backend"))

# ----------------------------------------------------------
# Imports
# ----------------------------------------------------------

from app.services.repository_review_engine import RepositoryReviewEngine
from app.analysis.dependency_graph import build_dependency_graph
from app.analysis.call_graph import build_call_graph
from app.services.repo_analyzer import analyze_repository


# ----------------------------------------------------------
# Pipeline Runner
# ----------------------------------------------------------

def run_pipeline(repo_path: str):

    print("Starting repository analysis...\n")

    # ------------------------------------------------------
    # Step 1: Repository Scan
    # ------------------------------------------------------

    files = analyze_repository(repo_path)

    # ------------------------------------------------------
    # Step 2: Dependency Graph
    # ------------------------------------------------------

    dependency_graph = build_dependency_graph(files)
    print("Dependency Graph:", dependency_graph)

    # ------------------------------------------------------
    # Step 3: Call Graph
    # ------------------------------------------------------

    call_graph = build_call_graph(files)
    print("Call Graph:", dict(call_graph))

    # ------------------------------------------------------
    # Step 4: AI Review Engine
    # ------------------------------------------------------

    print("\nRunning AI repository review...\n")

    engine = RepositoryReviewEngine()

    result = engine.review_repository(repo_path)

    summary = result["repository_summary"]
    reports = result["file_reports"]

    # ------------------------------------------------------
    # Step 5: Print Summary
    # ------------------------------------------------------

    print("\n================ REPOSITORY SUMMARY ================\n")

    print("Files analyzed:", summary["files_analyzed"])
    print("Files with issues:", summary["files_with_issues"])
    print("Average quality score:", summary["average_quality_score"])
    print("Total security issues:", summary["total_security_issues"])

    print("\n====================================================\n")

    # ------------------------------------------------------
    # Step 6: Print File Reports
    # ------------------------------------------------------

    for report in reports:
        print(report)
        print("-" * 60)


# ----------------------------------------------------------
# Script Entry Point
# ----------------------------------------------------------

if __name__ == "__main__":

    if len(sys.argv) > 1:
        repo_path = sys.argv[1]
    else:
        repo_path = "rag/data"

    run_pipeline(repo_path)