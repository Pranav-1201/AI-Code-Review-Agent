# ==========================================================
# File: tasks.py
# Purpose: Celery task definitions (Phase 6 / Chunk 5).
# ==========================================================
#
# The one task the queue carries today is a repository scan. It is deliberately
# thin: it defers to main.run_scan_pipeline, which already owns cloning, the
# incremental prior-store, analysis, and persisting progress/result to the scan
# store. Keeping the heavy logic in main.run_scan_pipeline means:
#   1. `import main` is LAZY (inside the task body), so this module and main.py
#      can import each other (main imports run_scan_task to enqueue it) without
#      a circular-import failure at load time.
#   2. The task resolves run_scan_pipeline as a *module attribute at call time*,
#      so the live-API tests that monkeypatch main.run_scan_pipeline still see
#      their stub under eager mode.

from backend.app.services.celery_app import celery_app


@celery_app.task(name="scan.run", bind=True)
def run_scan_task(self, scan_id: str, repo_url: str, explanation_depth: str = "senior"):
    """Run one repository scan out-of-process.

    Returns the scan result dict for observability, but callers do not rely on
    it — the authoritative progress/result is written to the SQLite scan store
    by run_scan_pipeline and read back via GET /scan/{id}.
    """
    import main  # lazy: see module docstring

    return main.run_scan_pipeline(scan_id, repo_url, explanation_depth)
