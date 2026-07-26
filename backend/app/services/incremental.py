"""
Incremental git-diff-aware re-analysis (Phase 6 / Chunk 5).

Re-scanning a repo re-runs the full per-file structural + AI pass on every
file even when only a handful changed. This module uses gitpython to find
what changed between the last-scanned commit and the current HEAD so the
engine can re-analyze only the changed files and reuse prior results for the
rest.

IMPORTANT — correctness boundary: this only decides which files get the
expensive PER-FILE pass. Cross-file reduces (interprocedural dead-function
detection, taint) still run over the FULL set in
repo_analyzer.analyze_repository, because an unchanged file's verdict can
depend on a file that did change.

Everything here is best-effort: a missing gitpython, a non-git path, or a
since-commit that isn't reachable (e.g. a shallow clone) makes the functions
return a sentinel (None) so the caller falls back to a full analysis. That
fallback is the caller's to log — it must never be silent.
"""

import os
import json
import hashlib
from typing import Optional, Set, List, Dict

# Sibling of the per-file CacheManager store, under backend/app/.cache/.
CACHE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), ".cache", "incremental"
)


def _repo(repo_path: str):
    # Imported lazily so a missing dependency degrades to full analysis
    # rather than breaking import of the whole analysis package.
    from git import Repo
    return Repo(repo_path)


def head_sha(repo_path: str) -> Optional[str]:
    """Current HEAD commit SHA, or None if the path isn't a usable git repo."""
    try:
        return _repo(repo_path).head.commit.hexsha
    except Exception:
        return None


def changed_files(repo_path: str, since_sha: str) -> Optional[Set[str]]:
    """Repo-relative (forward-slash) paths changed between since_sha and HEAD.

    Includes added / modified / renamed / copied paths (both sides of a
    rename). Deletions are irrelevant — a deleted file simply won't be in the
    current tree the caller walks.

    Returns None when the diff cannot be computed (missing dep, not a repo,
    unknown/unreachable since_sha, shallow clone) so the caller does a full
    analysis instead of silently under-analyzing.
    """
    if not since_sha:
        return None
    try:
        repo = _repo(repo_path)
        head = repo.head.commit
        try:
            base = repo.commit(since_sha)
        except Exception:
            return None  # since_sha not reachable in this clone -> full
        changed: Set[str] = set()
        for d in base.diff(head):
            for p in (d.a_path, d.b_path):
                if p:
                    changed.add(p.replace("\\", "/"))
        return changed
    except Exception:
        return None


# ----------------------------------------------------------
# Prior-scan store: last analysed (sha, per-file results) per repo.
# Content-independent, keyed by repo identifier (URL/path).
# ----------------------------------------------------------

def _key(repo_url: str) -> str:
    return hashlib.md5(repo_url.encode("utf-8")).hexdigest()


def load_prior(repo_url: str) -> Optional[Dict]:
    """Return {'sha': str, 'files': [dict, ...]} for a prior scan, or None."""
    path = os.path.join(CACHE_DIR, f"{_key(repo_url)}.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and "sha" in data and "files" in data:
            return data
    except Exception:
        pass
    return None


def save_prior(repo_url: str, sha: Optional[str], files: List[Dict]) -> None:
    """Persist the latest (sha, per-file results) for repo_url (atomic write)."""
    if not sha or files is None:
        return
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, f"{_key(repo_url)}.json")
    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"sha": sha, "files": files}, f)
        os.replace(tmp, path)  # atomic: readers never see a torn file
    except Exception:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass
