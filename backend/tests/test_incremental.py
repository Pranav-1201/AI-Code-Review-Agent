"""
Incremental git-diff re-analysis guards (Phase 6 / Chunk 5).

The load-bearing invariant: an incremental re-analysis (re-run only the
git-diff-changed files, reuse the rest) must produce the SAME result as a
full re-analysis of the same commit. A concurrency/reuse bug that dropped or
staled a file would be invisible to a test that only checked the changed
file, so test_incremental_equals_full compares the whole result — and passes
the prior through a JSON round-trip, exactly as the on-disk prior-store does.
"""

import json
import subprocess

import pytest

from backend.app.services import incremental
from backend.app.services.repo_analyzer import analyze_repository


def _git(repo, *args):
    # Never touch global git config (Defect G): identity via `git -c`.
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.email=t@t.local",
         "-c", "user.name=test", *args],
        check=True, capture_output=True,
    )


def _build_repo(root, n=6):
    root.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        (root / f"mod_{i}.py").write_text(
            f'"""Module {i}."""\n\ndef f_{i}(x):\n    return x + {i}\n',
            encoding="utf-8",
        )
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "v1")
    return root


def _norm(files):
    """Transport-equivalent normalization (how results are stored/sent)."""
    return json.dumps(files, sort_keys=True, default=str)


def test_head_sha_and_changed_files(tmp_path):
    repo = _build_repo(tmp_path / "repo")
    sha1 = incremental.head_sha(str(repo))
    assert sha1 and len(sha1) == 40

    (repo / "mod_2.py").write_text('"""Module 2 changed."""\n\ndef f_2(x):\n    return x * 2\n',
                                   encoding="utf-8")
    (repo / "new_file.py").write_text('def brand_new():\n    return 1\n', encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "v2")

    changed = incremental.changed_files(str(repo), sha1)
    assert changed == {"mod_2.py", "new_file.py"}, changed


def test_changed_files_unknown_since_returns_none(tmp_path):
    repo = _build_repo(tmp_path / "repo")
    # A SHA not in this repo's history -> None -> caller falls back to full.
    assert incremental.changed_files(str(repo), "0" * 40) is None


def test_incremental_equals_full(tmp_path, monkeypatch):
    # Isolate incremental logic from the process pool for determinism.
    monkeypatch.setenv("ANALYSIS_PARALLEL", "off")

    repo = _build_repo(tmp_path / "repo")
    full_v1 = analyze_repository(str(repo))
    sha1 = incremental.head_sha(str(repo))

    # Change exactly one file and add one; commit v2.
    (repo / "mod_3.py").write_text('"""Module 3 changed."""\n\ndef f_3(x):\n    return x - 3\n',
                                   encoding="utf-8")
    (repo / "extra.py").write_text('def extra():\n    return 42\n', encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "v2")

    # Prior comes off disk as JSON in production — round-trip to be faithful.
    prior = json.loads(json.dumps(full_v1, default=str))

    full_v2 = analyze_repository(str(repo))
    incr_v2 = analyze_repository(str(repo), since_sha=sha1, prior_files=prior)

    # Same files, same order.
    assert [f["file_path"] for f in incr_v2] == [f["file_path"] for f in full_v2]
    # Byte-identical (transport-normalized): incremental never drops/stales.
    assert _norm(incr_v2) == _norm(full_v2)


def test_incremental_falls_back_to_full_when_diff_unavailable(tmp_path, monkeypatch):
    monkeypatch.setenv("ANALYSIS_PARALLEL", "off")
    repo = _build_repo(tmp_path / "repo")
    full = analyze_repository(str(repo))
    prior = json.loads(json.dumps(full, default=str))

    # Unknown since_sha -> changed_files None -> full analysis, still correct.
    out = analyze_repository(str(repo), since_sha="0" * 40, prior_files=prior)
    assert _norm(out) == _norm(full)


def test_prior_store_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(incremental, "CACHE_DIR", str(tmp_path / "inc"))
    assert incremental.load_prior("repo-x") is None
    incremental.save_prior("repo-x", "a" * 40, [{"file_path": "a.py", "score": 90}])
    got = incremental.load_prior("repo-x")
    assert got["sha"] == "a" * 40
    assert got["files"][0]["file_path"] == "a.py"


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
