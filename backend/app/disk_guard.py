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
import subprocess
import sys
import threading
import time

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


def force_rmtree(path, attempts=10, delay=0.2):
    """rmtree that copes with BOTH ways Windows holds a git directory open.

    Two distinct failures, one function, because callers should not have to
    know which of them they are about to hit:

    1. git marks objects/pack/*.idx read-only, so unlinking raises
       PermissionError [WinError 5]. The onexc/onerror hook clears the
       read-only bit and retries that single file.

    2. A process that has just been killed does not release its open handles
       synchronously -- TerminateProcess signals the process object, but the
       kernel frees the handle a moment later. A delete issued in between
       raises PermissionError [WinError 32], a sharing violation, which no
       amount of chmod will fix. The bounded retry below waits it out.

    Retries are capped (default ~2s total) so a directory that is genuinely
    locked still raises rather than hanging the scan.

    Moved here from run_benchmark.py in Phase E: eviction and the clone
    watchdog both delete git directories, so all three callers need it.
    """
    def _retry_after_chmod(func, target, _exc):
        os.chmod(target, stat.S_IWRITE)
        func(target)

    for attempt in range(attempts):
        try:
            # shutil renamed the hook onerror -> onexc in 3.12 (onerror
            # deprecated). The handler signature is compatible with both.
            if sys.version_info >= (3, 12):
                shutil.rmtree(path, onexc=_retry_after_chmod)
            else:
                shutil.rmtree(path, onerror=_retry_after_chmod)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(delay)


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


# ----------------------------------------------------------
# Clone size watchdog
# ----------------------------------------------------------
#
# git has no native size limit, which is why this is a watchdog rather than a
# flag. Polling beats a pre-clone provider API query, which only covers hosts
# exposing a size endpoint, adds a network round-trip to the scan path, and is
# bypassed entirely by a self-hosted host. It beats a post-clone-only check
# because by then the disk has already absorbed the whole repository — that
# bounds the cache, not the peak.

GIT_CLONE_BASE = ["git", "-c", "http.postBuffer=524288000", "clone",
                  "--single-branch"]


class RepoTooLargeError(RuntimeError):
    """A repository exceeded MAX_REPO_MB during or after cloning."""

    def __init__(self, size_mb, limit_mb):
        super().__init__(
            f"Repository is {size_mb:.0f} MB, over the {limit_mb} MB limit"
        )
        self.size_mb = size_mb
        self.limit_mb = limit_mb


def clone_with_limit(url, dest, max_mb=None, timeout=300, poll_seconds=2.0,
                     command=None):
    """Clone `url` into `dest`, killing it if it grows past the cap.

    A daemon thread polls dest's size while git runs. On breach the process is
    killed and the partial clone deleted, so a hostile repository cannot leave
    gigabytes behind. A post-clone check covers a repository that finishes
    between two polls.

    `command` overrides the git argv and exists for tests; production callers
    leave it None.
    """
    limit_mb = max_mb if max_mb is not None else max_repo_mb()
    limit_bytes = limit_mb * 1024 * 1024

    # `git clone` parses a leading-dash argument as an option, and
    # --upload-pack=<cmd> executes <cmd>. api_guard.validate_repo_url already
    # requires an https:// URL on an allowlisted host, so this cannot be
    # reached through the API — but this helper is module-level and its next
    # caller may not go through that check, so the sink guards itself.
    if url.startswith("-"):
        raise ValueError(f"refusing to clone a URL that parses as a git option: {url!r}")

    # Any stale or partial directory from a previous attempt, cleared the way
    # that copes with git's read-only packfiles.
    if os.path.exists(dest):
        force_rmtree(dest)

    argv = command if command is not None else [*GIT_CLONE_BASE, "--", url, dest]
    proc = subprocess.Popen(argv)

    breach = {"size": None}
    done = threading.Event()

    def _watch():
        while not done.wait(poll_seconds):
            size = dir_size_bytes(dest)
            if size > limit_bytes:
                breach["size"] = size
                proc.kill()
                return

    watcher = threading.Thread(target=_watch, daemon=True)
    watcher.start()

    try:
        proc.wait(timeout=timeout)
    finally:
        done.set()
        watcher.join(timeout=5)

    if breach["size"] is not None:
        if os.path.exists(dest):
            force_rmtree(dest)
        raise RepoTooLargeError(breach["size"] / (1024 * 1024), limit_mb)

    if proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, argv)

    # The clone can finish inside one poll interval, so the cap is enforced
    # once more against the finished tree.
    final = dir_size_bytes(dest)
    if final > limit_bytes:
        force_rmtree(dest)
        raise RepoTooLargeError(final / (1024 * 1024), limit_mb)
