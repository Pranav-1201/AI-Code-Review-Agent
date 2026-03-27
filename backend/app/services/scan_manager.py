# ==========================================================
# File: scan_manager.py
# Purpose: Track repository scan progress
# ==========================================================

from typing import Dict
import uuid

SCAN_STATES: Dict[str, Dict] = {}


def create_scan(repo_url: str):

    scan_id = str(uuid.uuid4())

    SCAN_STATES[scan_id] = {
        "status": "starting",
        "progress": 0,
        "repo": repo_url,
        "result": None
    }

    return scan_id


def update_scan(scan_id: str, status: str, progress: int):

    if scan_id in SCAN_STATES:
        SCAN_STATES[scan_id]["status"] = status
        SCAN_STATES[scan_id]["progress"] = progress


def complete_scan(scan_id: str, result):

    if scan_id in SCAN_STATES:
        SCAN_STATES[scan_id]["status"] = "complete"
        SCAN_STATES[scan_id]["progress"] = 100
        SCAN_STATES[scan_id]["result"] = result


def get_scan(scan_id: str):

    return SCAN_STATES.get(scan_id)