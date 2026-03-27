# ==========================================================
# File: main.py
# Purpose: Entry point for AI repository code review
# Supports CLI + FastAPI + background scanning
# ==========================================================

import sys
import os


sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import subprocess
import tempfile
import shutil
from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

from backend.app.services.scan_manager import (
    create_scan,
    update_scan,
    complete_scan,
    get_scan
)

from backend.app.services.repository_review_engine import RepositoryReviewEngine
from backend.app.analysis.dependency_graph import build_dependency_graph
from backend.app.analysis.call_graph import build_call_graph
from backend.app.services.repo_analyzer import analyze_repository
from backend.app.services.pr_review_engine import review_pull_request


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
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ----------------------------------------------------------
# Request Model
# ----------------------------------------------------------

class RepoRequest(BaseModel):
    repo_path: str


# ----------------------------------------------------------
# Core Pipeline
# ----------------------------------------------------------

def run_pipeline(repo_path: str):

    print("Starting repository analysis...")

    files = analyze_repository(repo_path)

    print("Scanning repository at:", repo_path)
    print("Files found:", len(files))

    # Prevent extremely large repos
    if len(files) > 2000:
        files = files[:2000]

    dependency_graph = build_dependency_graph(files)
    call_graph = build_call_graph(files)

    print("Running AI repository review...")

    engine = RepositoryReviewEngine()
    # Pass analyzed files directly to review engine
    result = engine.review_repository(repo_path, files)

    return {
        "repository_summary": result["repository_summary"],
        "file_reports": result["file_reports"],
        "issues": result["issues"],
        "dependencies": result["dependencies"],
        "duplicates": result["duplicates"],
        "visualizations": result["visualizations"],
        "dependency_graph": dependency_graph,
        "call_graph": dict(call_graph)
    }


# ----------------------------------------------------------
# Background Scan Pipeline
# ----------------------------------------------------------

def run_scan_pipeline(scan_id: str, repo_url: str):

    temp_dir = tempfile.mkdtemp()
    repo_dir = os.path.join(temp_dir, "repo")

    try:

        update_scan(scan_id, "cloning repository", 10)

        subprocess.run(["git", "config", "--global", "http.postBuffer", "524288000"])

        subprocess.run(
            [
                "git",
                "clone",
                "--depth", "1",
                "--filter=blob:none",
                "--single-branch",
                repo_url,
                repo_dir
            ],
            check=True,
            timeout=120
        )

        update_scan(scan_id, "analyzing repository", 40)

        result = run_pipeline(repo_dir)

        update_scan(scan_id, "finalizing results", 80)

        complete_scan(scan_id, result)

    except Exception as e:

        complete_scan(scan_id, {"error": str(e)})

    finally:

        shutil.rmtree(temp_dir, ignore_errors=True)


# ----------------------------------------------------------
# API Routes
# ----------------------------------------------------------

@app.get("/")
def root():
    return {"message": "AI Code Review Agent Running"}


# Start Scan

@app.post("/scan")
def start_scan(request: RepoRequest, background_tasks: BackgroundTasks):

    scan_id = create_scan(request.repo_path)

    background_tasks.add_task(
        run_scan_pipeline,
        scan_id,
        request.repo_path
    )

    return {"scan_id": scan_id}


# Get Scan Progress

@app.get("/scan/{scan_id}")
def scan_status(scan_id: str):

    scan = get_scan(scan_id)

    if not scan:
        return {"error": "Scan not found"}

    return scan

@app.post("/github-webhook")
async def github_webhook(payload: dict):

    if payload.get("action") != "opened":
        return {"status": "ignored"}

    pr = payload["pull_request"]
    repo = payload["repository"]["full_name"]
    pr_number = pr["number"]

    review_pull_request(repo, pr_number)

    return {"status": "review_started"}

# ----------------------------------------------------------
# CLI Entry Point
# ----------------------------------------------------------

if __name__ == "__main__":

    if len(sys.argv) > 1:
        repo_path = sys.argv[1]
    else:
        repo_path = "rag/data"

    result = run_pipeline(repo_path)

    print(result)