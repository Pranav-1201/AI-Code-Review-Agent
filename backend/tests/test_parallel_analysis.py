"""
Parallel-dispatch guards for RepoAnalyzer.analyze_repository (Phase 6 / Chunk 5).

The per-file structural pass now fans out across processes. The one thing that
must never change is the OUTPUT: parallel execution must produce byte-identical
results to the old sequential loop — same files, same order, same fields. A
concurrency bug that dropped or reordered a file would be invisible to a test
that only exercised the isolated worker, so these tests compare the two modes
end-to-end on a real (temp) repo, and separately prove the pool actually runs
in multiple processes (guarding against a silent fallback to sequential).
"""

import os
import time
from concurrent.futures import ProcessPoolExecutor

import pytest

from backend.app.services.repo_analyzer import (
    analyze_repository,
    _resolve_worker_count,
)


def _build_repo(root, n_files=12):
    """Create n_files distinct Python modules (> the parallel threshold)."""
    root.mkdir(parents=True, exist_ok=True)
    for i in range(n_files):
        (root / f"mod_{i:02d}.py").write_text(
            f'"""Module {i}."""\n\n'
            f"def f_{i}(x):\n"
            f"    total = 0\n"
            f"    for j in range(x):\n"
            f"        if j % 2 == 0:\n"
            f"            total += j\n"
            f"    return total\n",
            encoding="utf-8",
        )
    # A nested dir + a taint sink, so the interprocedural reduce runs too.
    sub = root / "pkg"
    sub.mkdir()
    (sub / "views.py").write_text(
        "from flask import request\n\n"
        "def handler():\n"
        "    q = request.args['q']\n"
        "    return str(eval(q))\n",
        encoding="utf-8",
    )
    return root


def _run(root, mode):
    """Run analyze_repository under an explicit parallel mode."""
    prev = os.environ.get("ANALYSIS_PARALLEL")
    prev_thr = os.environ.get("ANALYSIS_PARALLEL_THRESHOLD")
    os.environ["ANALYSIS_PARALLEL"] = mode
    os.environ["ANALYSIS_PARALLEL_THRESHOLD"] = "4"  # ensure the repo crosses it
    try:
        return analyze_repository(str(root))
    finally:
        if prev is None:
            os.environ.pop("ANALYSIS_PARALLEL", None)
        else:
            os.environ["ANALYSIS_PARALLEL"] = prev
        if prev_thr is None:
            os.environ.pop("ANALYSIS_PARALLEL_THRESHOLD", None)
        else:
            os.environ["ANALYSIS_PARALLEL_THRESHOLD"] = prev_thr


def test_parallel_output_identical_to_sequential(tmp_path):
    """The product invariant: parallel == sequential, exactly."""
    repo = _build_repo(tmp_path / "repo")

    sequential = _run(repo, "off")
    parallel = _run(repo, "auto")

    # Same number of files, same order of file_paths (no drop, no reorder).
    seq_paths = [f["file_path"] for f in sequential]
    par_paths = [f["file_path"] for f in parallel]
    assert par_paths == seq_paths, (
        "parallel changed file set/order:\n"
        f"seq={seq_paths}\npar={par_paths}"
    )

    # Full per-file equality — catches any dropped/corrupted field.
    assert parallel == sequential, "parallel produced different per-file content"


def test_resolve_worker_count_gate(monkeypatch):
    monkeypatch.setenv("ANALYSIS_PARALLEL", "off")
    assert _resolve_worker_count(1000) == 1  # explicit off wins

    monkeypatch.setenv("ANALYSIS_PARALLEL", "auto")
    monkeypatch.setenv("ANALYSIS_PARALLEL_THRESHOLD", "8")
    assert _resolve_worker_count(3) == 1     # below threshold -> sequential

    monkeypatch.setenv("ANALYSIS_MAX_WORKERS", "3")
    assert _resolve_worker_count(100) == 3   # capped by configured max
    assert _resolve_worker_count(2) == 1     # below threshold still wins


# --- Proof the pool really executes in separate processes -------------------
# Defined at module level so ProcessPoolExecutor can pickle/import it in the
# spawned children (Windows spawn re-imports this module by name).

def _pid_probe(_):
    # The sleep is load-bearing, not padding. ProcessPoolExecutor spawns workers
    # LAZILY, so with instantaneous tasks the first worker can drain the whole
    # queue before a second one is ever created — the pool is behaving correctly
    # and the PID set still comes back with one entry. That made this test pass
    # on Windows (spawn, slow worker startup) and fail on the Linux CI runner
    # (fork, fast), which is exactly backwards from useful. Holding each task
    # open long enough to overlap forces the pool to actually use both workers.
    time.sleep(0.15)
    return os.getpid()


@pytest.mark.skipif((os.cpu_count() or 1) < 2, reason="needs >=2 cores")
def test_pool_runs_in_multiple_processes():
    # submit() up front rather than map(): every task is queued before any can
    # finish, so the pool has a reason to grow to max_workers.
    with ProcessPoolExecutor(max_workers=2) as ex:
        futures = [ex.submit(_pid_probe, i) for i in range(4)]
        pids = [f.result() for f in futures]

    assert os.getpid() not in pids, "work ran in the parent, not a child process"
    assert len(set(pids)) > 1, f"expected multiple worker PIDs, got {set(pids)}"


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
