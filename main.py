# ==========================================================
# File: main.py
# Purpose: Entry point for AI repository code review
# Supports both CLI and FastAPI
# ==========================================================

import sys
import os
from fastapi import FastAPI
from pydantic import BaseModel

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
from fastapi.middleware.cors import CORSMiddleware

# ----------------------------------------------------------
# Core Pipeline
# ----------------------------------------------------------

def run_pipeline(repo_path: str):

    print("Starting repository analysis...\n")

    files = analyze_repository(repo_path)

    dependency_graph = build_dependency_graph(files)
    print("Dependency Graph:", dependency_graph)

    call_graph = build_call_graph(files)
    print("Call Graph:", dict(call_graph))

    print("\nRunning AI repository review...\n")

    engine = RepositoryReviewEngine()
    result = engine.review_repository(repo_path)

    summary = result["repository_summary"]
    reports = result["file_reports"]

    print("\n================ REPOSITORY SUMMARY ================\n")

    print("Files analyzed:", summary["files_analyzed"])
    print("Files with issues:", summary["files_with_issues"])
    print("Average quality score:", summary["average_quality_score"])
    print("Total security issues:", summary["total_security_issues"])

    print("\n====================================================\n")

    for report in reports:
        print(report)
        print("-" * 60)

    return {
        "summary": summary,
        "reports": reports,
        "dependency_graph": dependency_graph,
        "call_graph": dict(call_graph)
    }


# ----------------------------------------------------------
# FastAPI App
# ----------------------------------------------------------

app = FastAPI(
    title="AI Repository Code Review Agent",
    description="AI-powered repository analysis",
    version="1.0"
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # for development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RepoRequest(BaseModel):
    repo_path: str


@app.get("/")
def root():
    return {"message": "AI Code Review Agent Running"}


@app.post("/analyze")
def analyze_repo(request: RepoRequest):

    result = run_pipeline(request.repo_path)

    return result


# ----------------------------------------------------------
# CLI Entry Point
# ----------------------------------------------------------

if __name__ == "__main__":

    if len(sys.argv) > 1:
        repo_path = sys.argv[1]
    else:
        repo_path = "rag/data"

    run_pipeline(repo_path)
