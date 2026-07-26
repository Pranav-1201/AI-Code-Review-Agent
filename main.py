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
from contextlib import asynccontextmanager
from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

from backend.app.services.scan_manager import (
    create_scan,
    update_scan,
    complete_scan,
    get_scan,
    recover_interrupted_scans,
)

from backend.app.services.repository_review_engine import RepositoryReviewEngine
from backend.app.analysis.dependency_graph import build_dependency_graph
from backend.app.analysis.call_graph import build_call_graph
from backend.app.services.repo_analyzer import analyze_repository
from backend.app.services.pr_review_engine import review_pull_request
from backend.app.services.settings_manager import load_settings, save_settings, reset_settings
from backend.database.review_repository import record_feedback, get_precision_estimate


# ----------------------------------------------------------
# FastAPI App
# ----------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Zombie-scan recovery (Phase 6 / Chunk 5): scan work runs in-process,
    # so any scan left non-terminal by a previous process was killed with
    # it and cannot resume. Reconcile those rows once at startup so the UI
    # never polls a dead scan forever.
    try:
        recovered = recover_interrupted_scans()
        if recovered:
            print(f"[startup] recovered {recovered} interrupted scan(s) from a previous run")
    except Exception as e:  # never block startup on recovery
        print(f"[startup] scan recovery skipped: {e!r}")
    yield


app = FastAPI(
    title="AI Repository Code Review Agent",
    description="AI-powered repository analysis",
    version="1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ----------------------------------------------------------
# Request Models
# ----------------------------------------------------------

class RepoRequest(BaseModel):
    repo_path: str
    explanation_depth: str = "senior"   # PHASE 5: junior | senior


class FeedbackRequest(BaseModel):
    review_id: int
    finding_key: str        # identifies the finding, e.g. "file.py:42:eval"
    vote: str               # "up" (true positive) | "down" (false positive)


# ----------------------------------------------------------
# Core Pipeline
# ----------------------------------------------------------

def run_pipeline(repo_path: str, scan_id: str = None, explanation_depth: str = "senior"):

    if scan_id:
        update_scan(scan_id, "analyzing", 20,
                    stage="discovery", stage_detail="Scanning repository files...")

    print("Starting repository analysis...")

    files = analyze_repository(repo_path)

    print("Scanning repository at:", repo_path)
    print("Files found:", len(files))

    if scan_id:
        update_scan(scan_id, "analyzing", 30,
                    stage="discovery", stage_detail=f"Found {len(files)} files",
                    total_files=len(files))

    # Prevent extremely large repos
    settings = load_settings()
    max_files = settings.get("analysis", {}).get("max_files", 2000)
    if len(files) > max_files:
        files = files[:max_files]

    if scan_id:
        update_scan(scan_id, "analyzing", 35,
                    stage="dependencies", stage_detail="Building dependency graph...")

    dependency_graph = build_dependency_graph(files)
    call_graph = build_call_graph(files)

    if scan_id:
        update_scan(scan_id, "analyzing", 40,
                    stage="analysis", stage_detail="Running AI code review...")

    print("Running AI repository review...")

    engine = RepositoryReviewEngine()
    result = engine.review_repository(repo_path, files, explanation_depth=explanation_depth)

    return {
        "repository_summary": result["repository_summary"],
        "file_reports": result["file_reports"],
        "issues": result["issues"],
        "dependencies": result["dependencies"],
        "duplicates": result["duplicates"],
        "visualizations": result["visualizations"],
        "insights": result.get("insights", {}),
        "dependency_graph": dependency_graph,
        "call_graph": dict(call_graph)
    }


# ----------------------------------------------------------
# Background Scan Pipeline
# ----------------------------------------------------------

def run_scan_pipeline(scan_id: str, repo_url: str, explanation_depth: str = "senior"):

    temp_dir = tempfile.mkdtemp()
    repo_dir = os.path.join(temp_dir, "repo")

    try:

        update_scan(scan_id, "cloning", 5,
                    stage="cloning", stage_detail="Cloning repository...")

        # Defect G: apply the large-repo post-buffer to THIS clone only,
        # via `git -c`, instead of mutating the user's global git config.
        subprocess.run(
            [
                "git",
                "-c", "http.postBuffer=524288000",
                "clone",
                "--depth", "1",
                "--single-branch",
                repo_url,
                repo_dir
            ],
            check=True,
            timeout=120
        )

        update_scan(scan_id, "analyzing", 15,
                    stage="cloning", stage_detail="Repository cloned successfully")

        result = run_pipeline(repo_dir, scan_id=scan_id, explanation_depth=explanation_depth)

        update_scan(scan_id, "finalizing", 90,
                    stage="finalizing", stage_detail="Computing health score...")

        print(f"DEBUG: run_pipeline returned {type(result)} with {len(result) if isinstance(result, list) else 'N/A'} items")
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
        request.repo_path,
        request.explanation_depth
    )

    return {"scan_id": scan_id}


# Get Scan Progress

@app.get("/scan/{scan_id}")
def scan_status(scan_id: str):

    scan = get_scan(scan_id)

    if not scan:
        return {"error": "Scan not found"}

    return scan


# ----------------------------------------------------------
# Settings API
# ----------------------------------------------------------

@app.get("/settings")
def get_settings():
    return load_settings()


@app.post("/settings")
def update_settings(settings: dict):
    saved = save_settings(settings)
    return {"status": "saved", "settings": saved}


@app.post("/settings/reset")
def reset_all_settings():
    defaults = reset_settings()
    return {"status": "reset", "settings": defaults}


# ----------------------------------------------------------
# Feedback API (Phase 5)
# Thumbs up/down on a finding, persisted to the DB, plus a
# running precision estimate (up / (up + down)).
# ----------------------------------------------------------

@app.post("/feedback")
def submit_feedback(feedback: FeedbackRequest):
    try:
        feedback_id = record_feedback(
            feedback.review_id, feedback.finding_key, feedback.vote
        )
    except ValueError as e:
        return {"status": "error", "detail": str(e)}
    return {"status": "recorded", "feedback_id": feedback_id,
            "precision": get_precision_estimate()}


@app.get("/feedback/precision")
def feedback_precision():
    return get_precision_estimate()


# ----------------------------------------------------------
# GitHub Webhook
# ----------------------------------------------------------

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