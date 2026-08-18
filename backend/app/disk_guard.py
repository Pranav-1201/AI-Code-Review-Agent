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


# ----------------------------------------------------------
# LRU cache eviction
# ----------------------------------------------------------
#
# Runs inline at the top of run_scan_pipeline, before the clone. Not on a
# schedule: Celery beat would mean a fourth compose service and a code path
# that cannot run in eager mode, which is the one thing Phase E could not
# verify locally. The cost here is a directory-stat sweep against a git clone,
# which is noise. The accepted tradeoff is that a fully idle deployment
# reclaims nothing until the next scan — an idle deployment is also not
# filling its disk.

def _cache_entries(clone_cache, prior_cache):
    """Map cache key -> (last_scan_time, total_bytes) across both caches.

    Recency comes from the PRIOR file's mtime, not the clone directory's. The
    prior is written exactly once per completed scan (incremental.save_prior),
    so its mtime is an accurate record of when the repo was last scanned. A
    clone directory's mtime moves for reasons unrelated to scanning: a fetch
    that found nothing, an editor or indexer, an antivirus pass.
    """
    entries = {}

    if os.path.isdir(clone_cache):
        for name in os.listdir(clone_cache):
            path = os.path.join(clone_cache, name)
            if os.path.isdir(path):
                entries[name] = [0.0, dir_size_bytes(path)]

    if os.path.isdir(prior_cache):
        for name in os.listdir(prior_cache):
            if not name.endswith(".json"):
                continue
            key = name[: -len(".json")]
            path = os.path.join(prior_cache, name)
            try:
                mtime = os.path.getmtime(path)
                size = os.path.getsize(path)
            except OSError:
                continue
            record = entries.setdefault(key, [0.0, 0])
            record[0] = mtime
            record[1] += size

    # A clone with no prior (a scan that died before save_prior) keeps mtime
    # 0.0, which sorts it first — correct: it is the least useful entry held.
    return {key: tuple(value) for key, value in entries.items()}


def _evict_one(clone_cache, prior_cache, key):
    """Remove a key's clone and prior together.

    Order matters only for crash safety: dropping the prior first means an
    interrupted eviction leaves a clone with no prior, which run_scan_pipeline
    handles by doing a full scan. The reverse would leave a prior pointing at
    a clone that no longer exists.
    """
    prior = os.path.join(prior_cache, f"{key}.json")
    if os.path.exists(prior):
        try:
            os.remove(prior)
        except OSError:
            pass

    clone = os.path.join(clone_cache, key)
    if os.path.isdir(clone):
        force_rmtree(clone)


def evict_caches(clone_cache, prior_cache, max_mb=None, keep=None):
    """Delete least-recently-scanned repos until both caches fit the cap.

    `keep` is the cache key of the repository about to be scanned; it is never
    evicted, so a sweep can't delete the cache it is a second away from using.

    Returns the list of evicted keys, oldest first. Empty means nothing was
    over the cap — the common case.
    """
    limit_bytes = (max_mb if max_mb is not None else max_cache_mb()) * 1024 * 1024
    entries = _cache_entries(clone_cache, prior_cache)
    total = sum(size for _mtime, size in entries.values())

    if total <= limit_bytes:
        return []

    candidates = sorted(
        ((key, mtime, size) for key, (mtime, size) in entries.items()
         if key != keep),
        key=lambda item: item[1],
    )

    evicted = []
    for key, _mtime, size in candidates:
        if total <= limit_bytes:
            break
        _evict_one(clone_cache, prior_cache, key)
        total -= size
        evicted.append(key)

    return evicted
