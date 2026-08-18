# ==========================================================
# File: disk_guard.py
# Purpose: Bound the disk this service can consume (Phase E — ops hardening).
# ==========================================================
#
# Two unbounded growth paths existed before this module:
#
#   1. CLONE_CACHE (main.py) keeps a persistent FULL clone per distinct
#      repo_url — deliberately not shallow, because a re-scan diffs history —
#      and incremental.CACHE_DIR keeps a parallel per-repo prior. Neither was
#      ever evicted. A long-lived worker scanning many repos fills the volume.
#
#   2. Nothing bounded the size of a single repository. git has no native size
#      limit and the 300s clone timeout is not one: a fast link moves many
#      gigabytes well inside 300 seconds.
#
# ENV (all read at CALL time, never at import time — the api_guard.py idiom;
# celery_app.py reads at import time and is correspondingly painful to test):
#   MAX_CACHE_MB   Combined ceiling across both caches. Default 5120.
#   MAX_REPO_MB    Ceiling on a single cloned repository. Default 1024.

import os
import shutil
import stat
import sys

DEFAULT_MAX_CACHE_MB = 5120
DEFAULT_MAX_REPO_MB = 1024


def _int_env(name, default):
    """Read an int from env at call time; fall back on anything unparseable."""
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def max_cache_mb():
    return _int_env("MAX_CACHE_MB", DEFAULT_MAX_CACHE_MB)


def max_repo_mb():
    return _int_env("MAX_REPO_MB", DEFAULT_MAX_REPO_MB)


def force_rmtree(path):
    """rmtree that copes with git's read-only pack files.

    git marks objects/pack/*.idx read-only; on Windows unlinking those raises
    PermissionError [WinError 5]. Passing ignore_errors=True "fixes" that by
    leaving the directory in place, which then makes `git clone` fail with exit
    128 on a non-empty destination — a worse symptom than the original.
    Clearing the read-only bit and retrying is the actual fix, and a genuine
    failure is allowed to propagate so the caller can report it.

    Moved here from run_benchmark.py in Phase E: eviction and the clone
    watchdog both delete git directories, so all three callers need it.
    """
    def _retry_after_chmod(func, target, _exc):
        os.chmod(target, stat.S_IWRITE)
        func(target)

    # shutil renamed the hook onerror -> onexc in 3.12 (onerror deprecated).
    # The handler signature is compatible with both.
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=_retry_after_chmod)
    else:
        shutil.rmtree(path, onerror=_retry_after_chmod)


def dir_size_bytes(path):
    """Recursive size of `path` in bytes; 0 if it does not exist.

    Files that vanish between the walk and the stat are skipped rather than
    raising: the watchdog reads a directory git is actively writing into, so
    a disappearing temp object is normal, not an error.
    """
    if not os.path.isdir(path):
        try:
            return os.path.getsize(path)
        except OSError:
            return 0

    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                continue
    return total
