# Phase E — Ops Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bound the disk this service can consume, make its runtime legible through structured logs and optional Sentry reporting, and stop shipping multi-gigabyte ML dependencies that no shipped configuration can reach.

**Architecture:** Two new modules under `backend/app/`, each holding one boundary in one readable file, following the cohesion principle `api_guard.py` states for itself. `disk_guard.py` owns LRU cache eviction, the clone size watchdog, and the filesystem helpers both need. `observability.py` owns JSON logging and Sentry initialization. Every environment variable is read at **call time**, never import time — the constraint that makes `api_guard` testable without reloading `main`.

**Tech Stack:** Python 3.11, FastAPI, Celery, pytest, `sentry-sdk` (new base dependency), pip-compile for lock generation.

**Spec:** `docs/superpowers/specs/2026-08-18-phase-e-ops-hardening-design.md` (commit `ad3ea5f`)

## Global Constraints

- **Branch:** `phase-e/ops-hardening`, based on `ac23d8e`.
- **Backend test command is `.\venv\Scripts\python.exe -m pytest`.** The global Python 3.13 has no fastapi and dies at collection. Never invoke bare `python -m pytest`.
- **Frontend typecheck is `npx tsc -b`.** Never bare `tsc --noEmit` — the root `tsconfig.json` is solution-style (`"files": []` plus references) and compiles zero files, exiting 0 unconditionally.
- **Baseline to preserve:** pytest **288 passed, 0 failed**; `run_benchmark.py --gate` exit **0**; `npx tsc -b` exit 0; `npm run build` exit 0.
- **All env vars read at call time**, inside a function, never at module import. Do not copy `celery_app.py`'s import-time reads.
- **No AI/assistant attribution** in any commit message. No `Co-Authored-By`, no "Generated with". See `CLAUDE.md`.
- **Docker is not installed on this machine.** Image build and boot are CI-verified or user-verified. Never claim them as verified locally.
- **Env var defaults (exact):** `LOG_LEVEL=INFO`, `LOG_FORMAT=text`, `SENTRY_DSN` unset, `SENTRY_ENVIRONMENT=development`, `SENTRY_TRACES_SAMPLE_RATE=0.0`, `MAX_CACHE_MB=5120`, `MAX_REPO_MB=1024`.
- **Commit after every task.** Do not batch two tasks into one commit.

## File Structure

**Created:**

| File | Responsibility |
|---|---|
| `backend/app/disk_guard.py` | Cache eviction, clone size watchdog, `force_rmtree` / `dir_size_bytes` helpers. |
| `backend/app/observability.py` | JSON log formatter, `configure_logging`, scan-id contextvar, `init_sentry`. |
| `backend/tests/test_disk_guard.py` | Behavioural tests for eviction ordering, the cap, pairing, and the watchdog. |
| `backend/tests/test_observability.py` | Tests for formatter output, idempotency, contextvar propagation, Sentry on/off. |
| `requirements-ml.txt` | The four ML dependencies plus the CPU-torch extra index URL. |
| `requirements-ml.lock` | pip-compiled lock for the above. |

**Modified:**

| File | Change |
|---|---|
| `backend/benchmark/run_benchmark.py:223-243` | Delete local `_force_rmtree`; import the shared one. Drop now-unused `shutil` / `stat` imports. |
| `main.py:225-265` | Call `evict_caches` before cloning; replace the raw `git clone` with `clone_with_limit`; wrap the pipeline in `scan_context`. |
| `main.py` lifespan (`:55-73`) | Call `configure_logging()` then `init_sentry()`. |
| `backend/app/services/celery_app.py:61` | Same two calls in `_recover_on_worker_ready`. |
| `backend/app/services/retriever_service.py:6,11` | Move `faiss` / `sentence_transformers` imports inside functions; catch `ImportError`. |
| `backend/app/services/llm_service.py:12` | Move the `CodeRetriever` import to its instantiation site (`:83`). |
| `requirements.txt` | Remove the four ML deps and the `--extra-index-url` line; add `sentry-sdk`. |
| `requirements.lock` | Regenerate with pip-compile. |
| `backend/Dockerfile` | Add `ENV LOG_FORMAT=json`. |
| `.env.example` | Document all seven new variables. |
| `DEPLOYMENT.md` | New operations section. |

---

### Task 1: Shared filesystem helpers

Extract the working `_force_rmtree` rather than writing a third copy of a bug already solved once: git marks `objects/pack/*.idx` read-only, so `shutil.rmtree` raises `PermissionError` (WinError 5) on Windows, and `ignore_errors=True` "fixes" it by leaving the directory behind — which then makes the next `git clone` fail with exit 128 on a non-empty destination.

**Files:**
- Create: `backend/app/disk_guard.py`
- Create: `backend/tests/test_disk_guard.py`
- Modify: `backend/benchmark/run_benchmark.py:223-243` (delete `_force_rmtree`), `:32,33` (drop `shutil`, `stat` imports), `:44` area (add import)

**Interfaces:**
- Consumes: nothing.
- Produces: `force_rmtree(path: str | os.PathLike) -> None`, `dir_size_bytes(path: str | os.PathLike) -> int`. Both accept `str` or `Path`. `dir_size_bytes` returns `0` for a missing path and never raises on a file that vanishes mid-walk.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_disk_guard.py`:

```python
"""
Disk-bounding guards (Phase E — ops hardening).

Two failure modes are under test here, both of which the service was open to
before this module existed: caches that grow until the volume is full, and a
single hostile or huge repository that exhausts the disk mid-clone. The 300s
clone timeout was never a size limit — a fast link moves many gigabytes well
inside it.
"""

import os
import stat
import subprocess
import sys
import textwrap

import pytest

from backend.app import disk_guard


def test_force_rmtree_removes_read_only_files(tmp_path):
    """git marks pack indexes read-only; plain rmtree raises WinError 5."""
    victim = tmp_path / "repo"
    victim.mkdir()
    locked = victim / "packed.idx"
    locked.write_text("data")
    os.chmod(locked, stat.S_IREAD)

    disk_guard.force_rmtree(victim)

    assert not victim.exists()


def test_dir_size_bytes_sums_nested_files(tmp_path):
    (tmp_path / "a").write_bytes(b"x" * 100)
    nested = tmp_path / "sub" / "deep"
    nested.mkdir(parents=True)
    (nested / "b").write_bytes(b"y" * 250)

    assert disk_guard.dir_size_bytes(tmp_path) == 350


def test_dir_size_bytes_missing_path_is_zero(tmp_path):
    assert disk_guard.dir_size_bytes(tmp_path / "nope") == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.\venv\Scripts\python.exe -m pytest backend/tests/test_disk_guard.py -v`

Expected: FAIL at collection with `ModuleNotFoundError: No module named 'backend.app.disk_guard'`.

- [ ] **Step 3: Write the implementation**

Create `backend/app/disk_guard.py`:

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.\venv\Scripts\python.exe -m pytest backend/tests/test_disk_guard.py -v`

Expected: 3 passed.

- [ ] **Step 5: Repoint the benchmark at the shared helper**

In `backend/benchmark/run_benchmark.py`, delete the entire `_force_rmtree` function (lines 223-243, from `def _force_rmtree(path):` through the `shutil.rmtree(path, onerror=_retry_after_chmod)` line and its closing blank line).

Add to the existing import block, beside the other `backend.` imports around line 43:

```python
from backend.app.disk_guard import force_rmtree
```

Change the single call site (was line 270, inside `_ensure_clone`):

```python
        force_rmtree(dest)
```

Delete these two now-unused imports from the header block:

```python
import shutil
import stat
```

Keep `import sys` — it is still used at lines 41 and 425.

- [ ] **Step 6: Verify the benchmark still runs and nothing else broke**

Run: `.\venv\Scripts\python.exe -m pytest backend/tests/ -q`

Expected: 291 passed (288 baseline + 3 new), 0 failed.

Run: `.\venv\Scripts\python.exe backend/benchmark/run_benchmark.py --gate`

Expected: exit 0.

- [ ] **Step 7: Commit**

```bash
git add backend/app/disk_guard.py backend/tests/test_disk_guard.py backend/benchmark/run_benchmark.py
git commit -F - <<'EOF'
Extract force_rmtree into a shared disk_guard module

Eviction and the clone watchdog both delete git directories, so both hit
the read-only packfile problem run_benchmark already solved: git marks
objects/pack/*.idx read-only, rmtree raises WinError 5 on Windows, and
ignore_errors=True leaves the directory behind so the next clone dies
with exit 128 on a non-empty destination.

Moving the working implementation beats writing a third copy of it.
Adds dir_size_bytes alongside, which both new callers also need; it
skips files that vanish mid-walk because the watchdog reads a directory
git is actively writing into.
EOF
```

---

### Task 2: LRU cache eviction

**Files:**
- Modify: `backend/app/disk_guard.py` (add `evict_caches`)
- Modify: `backend/tests/test_disk_guard.py` (add eviction tests)
- Modify: `main.py:225-231` (call it before cloning)
- Modify: `.env.example` (document `MAX_CACHE_MB`)

**Interfaces:**
- Consumes: `force_rmtree`, `dir_size_bytes`, `max_cache_mb` from Task 1.
- Produces: `evict_caches(clone_cache: str, prior_cache: str, max_mb: int | None = None, keep: str | None = None) -> list[str]` — returns the list of evicted keys (md5 hex strings), empty when nothing was over the cap.

**Key design points the tests pin:**

- Both caches key on the same `md5(repo_url).hexdigest()`. `CLONE_CACHE/<key>` is a directory; `CACHE_DIR/<key>.json` is a file.
- **A clone and its prior are always evicted together.** A surviving prior whose clone is gone is safe — `run_scan_pipeline` gates on `prior and os.path.isdir(repo_dir/".git")` and falls through to a full clone. The reverse silently loses history diffing while reporting nothing wrong.
- **Recency comes from the prior JSON's mtime**, not the clone directory's. The prior is written exactly once per completed scan by `incremental.save_prior`; a clone directory's mtime moves for unrelated reasons (a fetch that found nothing, an indexer, antivirus).
- `keep` protects the repository about to be scanned so eviction never deletes the cache it is one second away from using.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_disk_guard.py`:

```python
def _seed(clone_cache, prior_cache, key, clone_bytes, mtime):
    """Create a clone dir + matching prior file for `key`, with a set mtime."""
    repo = clone_cache / key
    (repo / ".git").mkdir(parents=True)
    (repo / "payload.bin").write_bytes(b"z" * clone_bytes)

    prior = prior_cache / f"{key}.json"
    prior.write_text('{"sha": "abc", "files": []}')
    os.utime(prior, (mtime, mtime))
    return repo, prior


@pytest.fixture()
def caches(tmp_path):
    clone_cache = tmp_path / "clones"
    prior_cache = tmp_path / "priors"
    clone_cache.mkdir()
    prior_cache.mkdir()
    return clone_cache, prior_cache


def test_under_cap_evicts_nothing(caches):
    clone_cache, prior_cache = caches
    _seed(clone_cache, prior_cache, "aaa", 1000, mtime=1000)

    evicted = disk_guard.evict_caches(
        str(clone_cache), str(prior_cache), max_mb=1
    )

    assert evicted == []
    assert (clone_cache / "aaa").exists()


def test_evicts_least_recently_scanned_first(caches):
    clone_cache, prior_cache = caches
    one_mb = 1024 * 1024
    _seed(clone_cache, prior_cache, "old", one_mb, mtime=1000)
    _seed(clone_cache, prior_cache, "mid", one_mb, mtime=2000)
    _seed(clone_cache, prior_cache, "new", one_mb, mtime=3000)

    # Cap of 2 MB against ~3 MB held: exactly one repo must go, the oldest.
    evicted = disk_guard.evict_caches(
        str(clone_cache), str(prior_cache), max_mb=2
    )

    assert evicted == ["old"]
    assert not (clone_cache / "old").exists()
    assert (clone_cache / "mid").exists()
    assert (clone_cache / "new").exists()


def test_eviction_removes_clone_and_prior_together(caches):
    clone_cache, prior_cache = caches
    one_mb = 1024 * 1024
    _seed(clone_cache, prior_cache, "old", one_mb, mtime=1000)
    _seed(clone_cache, prior_cache, "new", one_mb, mtime=3000)

    disk_guard.evict_caches(str(clone_cache), str(prior_cache), max_mb=1)

    # An orphaned prior would make a later scan diff against a clone that is
    # gone; the pair must disappear atomically.
    assert not (clone_cache / "old").exists()
    assert not (prior_cache / "old.json").exists()


def test_keep_protects_the_repo_about_to_be_scanned(caches):
    clone_cache, prior_cache = caches
    one_mb = 1024 * 1024
    _seed(clone_cache, prior_cache, "old", one_mb, mtime=1000)
    _seed(clone_cache, prior_cache, "new", one_mb, mtime=3000)

    evicted = disk_guard.evict_caches(
        str(clone_cache), str(prior_cache), max_mb=1, keep="old"
    )

    # "old" is the LRU but is the scan target, so "new" goes instead.
    assert evicted == ["new"]
    assert (clone_cache / "old").exists()


def test_clone_without_a_prior_is_still_evictable(caches):
    """A scan that crashed before save_prior leaves a clone with no prior."""
    clone_cache, prior_cache = caches
    orphan = clone_cache / "orphan"
    (orphan / ".git").mkdir(parents=True)
    (orphan / "payload.bin").write_bytes(b"z" * (2 * 1024 * 1024))

    evicted = disk_guard.evict_caches(
        str(clone_cache), str(prior_cache), max_mb=1
    )

    assert evicted == ["orphan"]
    assert not orphan.exists()


def test_missing_cache_directories_are_not_an_error(tmp_path):
    assert disk_guard.evict_caches(
        str(tmp_path / "nope"), str(tmp_path / "also-nope")
    ) == []


def test_max_cache_mb_reads_env_at_call_time(monkeypatch):
    monkeypatch.setenv("MAX_CACHE_MB", "77")
    assert disk_guard.max_cache_mb() == 77
    monkeypatch.delenv("MAX_CACHE_MB")
    assert disk_guard.max_cache_mb() == disk_guard.DEFAULT_MAX_CACHE_MB
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.\venv\Scripts\python.exe -m pytest backend/tests/test_disk_guard.py -v`

Expected: the 3 Task-1 tests pass; the 7 new ones FAIL with `AttributeError: module 'backend.app.disk_guard' has no attribute 'evict_caches'`.

- [ ] **Step 3: Write the implementation**

Append to `backend/app/disk_guard.py`:

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.\venv\Scripts\python.exe -m pytest backend/tests/test_disk_guard.py -v`

Expected: 10 passed.

- [ ] **Step 5: Wire it into the scan pipeline**

In `main.py`, add to the import block beside the other `backend.app` imports (near line 24):

```python
from backend.app import disk_guard
```

In `run_scan_pipeline`, immediately after the two existing lines that compute the cache paths (currently lines 227-228):

```python
    os.makedirs(CLONE_CACHE, exist_ok=True)
    repo_dir = os.path.join(CLONE_CACHE, hashlib.md5(repo_url.encode("utf-8")).hexdigest())
```

insert:

```python
    # Bound the disk before adding to it. `keep` is this scan's own key so a
    # sweep can never delete the cached clone this run is about to reuse.
    disk_guard.evict_caches(
        CLONE_CACHE,
        incremental.CACHE_DIR,
        keep=os.path.basename(repo_dir),
    )
```

- [ ] **Step 6: Document the variable**

Append to `.env.example`, following the existing commented-default style:

```
# ----------------------------------------------------------
# Disk ceilings (backend/app/disk_guard.py)
# ----------------------------------------------------------

# Combined ceiling in MB across the clone cache and the incremental prior
# store. When exceeded, least-recently-scanned repositories are evicted
# (clone and prior together) at the start of the next scan.
# MAX_CACHE_MB=5120
```

- [ ] **Step 7: Run the full suite**

Run: `.\venv\Scripts\python.exe -m pytest backend/tests/ -q`

Expected: 298 passed (288 baseline + 10 new), 0 failed.

- [ ] **Step 8: Commit**

```bash
git add backend/app/disk_guard.py backend/tests/test_disk_guard.py main.py .env.example
git commit -F - <<'EOF'
Evict least-recently-scanned repos when the caches exceed a cap

Closes the Chunk 5 deferral. CLONE_CACHE keeps a full clone per distinct
repo_url and incremental.CACHE_DIR keeps a matching prior; neither was
ever evicted, so a long-lived worker scanning many repos filled the
volume. Accepted at the time only on condition it be fixed when real
deployment work began.

Evicts the clone and its prior as a pair. The dangerous direction is an
orphaned prior: run_scan_pipeline gates on prior AND a live .git dir, so
a prior whose clone is gone falls through to a full clone correctly,
while a clone whose prior is gone silently stops diffing history and
reports nothing unusual.

Recency comes from the prior JSON's mtime, not the clone directory's --
save_prior writes it exactly once per completed scan, whereas a clone
dir's mtime moves for a fetch that found nothing, an indexer, or an
antivirus pass.

Runs inline before each clone rather than on a schedule; beat would add
a compose service and a path that cannot run in eager mode.
EOF
```

---

### Task 3: Clone size watchdog

**Files:**
- Modify: `backend/app/disk_guard.py` (add `RepoTooLargeError`, `clone_with_limit`)
- Modify: `backend/tests/test_disk_guard.py` (add watchdog tests)
- Modify: `main.py:257-265` (replace the raw clone)
- Modify: `.env.example` (document `MAX_REPO_MB`)

**Interfaces:**
- Consumes: `force_rmtree`, `dir_size_bytes`, `max_repo_mb` from Tasks 1-2.
- Produces:
  - `class RepoTooLargeError(RuntimeError)` with attributes `size_mb: float` and `limit_mb: int`.
  - `clone_with_limit(url: str, dest: str, max_mb: int | None = None, timeout: int = 300, poll_seconds: float = 2.0, command: list[str] | None = None) -> None`. Raises `RepoTooLargeError` on breach, `subprocess.CalledProcessError` on a non-zero git exit, `subprocess.TimeoutExpired` on timeout. `command` exists so tests can substitute a fake clone; production callers leave it `None`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_disk_guard.py`:

```python
def _growing_clone_command(dest, total_mb, chunk_mb=1, delay=0.05):
    """A fake `git clone`: creates dest and grows a file inside it.

    Used instead of a real clone so the watchdog is tested against observable
    growth without a network dependency in the suite.
    """
    script = textwrap.dedent(
        f"""
        import os, time
        os.makedirs({str(dest)!r}, exist_ok=True)
        with open(os.path.join({str(dest)!r}, "big.bin"), "wb") as fh:
            for _ in range({total_mb} // {chunk_mb}):
                fh.write(b"x" * ({chunk_mb} * 1024 * 1024))
                fh.flush()
                os.fsync(fh.fileno())
                time.sleep({delay})
        """
    )
    return [sys.executable, "-c", script]


def test_watchdog_kills_a_clone_that_exceeds_the_cap(tmp_path):
    dest = tmp_path / "huge"

    with pytest.raises(disk_guard.RepoTooLargeError) as excinfo:
        disk_guard.clone_with_limit(
            "https://example.invalid/huge.git",
            str(dest),
            max_mb=2,
            poll_seconds=0.05,
            command=_growing_clone_command(dest, total_mb=40),
        )

    assert excinfo.value.limit_mb == 2
    # The partial clone must not be left behind eating disk.
    assert not dest.exists()


def test_a_small_clone_completes_untouched(tmp_path):
    """The guard must not be passing by killing everything."""
    dest = tmp_path / "small"

    disk_guard.clone_with_limit(
        "https://example.invalid/small.git",
        str(dest),
        max_mb=64,
        poll_seconds=0.05,
        command=_growing_clone_command(dest, total_mb=2),
    )

    assert dest.exists()
    assert (dest / "big.bin").exists()


def test_a_failing_clone_raises_called_process_error(tmp_path):
    dest = tmp_path / "broken"

    with pytest.raises(subprocess.CalledProcessError):
        disk_guard.clone_with_limit(
            "https://example.invalid/broken.git",
            str(dest),
            max_mb=64,
            poll_seconds=0.05,
            command=[sys.executable, "-c", "raise SystemExit(128)"],
        )


def test_post_clone_check_catches_a_repo_that_slipped_past_polling(tmp_path):
    """A clone can finish between two polls; the size check must still fire."""
    dest = tmp_path / "fast"
    script = textwrap.dedent(
        f"""
        import os
        os.makedirs({str(dest)!r}, exist_ok=True)
        with open(os.path.join({str(dest)!r}, "big.bin"), "wb") as fh:
            fh.write(b"x" * (4 * 1024 * 1024))
        """
    )

    with pytest.raises(disk_guard.RepoTooLargeError):
        disk_guard.clone_with_limit(
            "https://example.invalid/fast.git",
            str(dest),
            max_mb=1,
            poll_seconds=30,  # guarantees no poll fires before the process ends
            command=[sys.executable, "-c", script],
        )

    assert not dest.exists()


def test_max_repo_mb_reads_env_at_call_time(monkeypatch):
    monkeypatch.setenv("MAX_REPO_MB", "42")
    assert disk_guard.max_repo_mb() == 42
    monkeypatch.delenv("MAX_REPO_MB")
    assert disk_guard.max_repo_mb() == disk_guard.DEFAULT_MAX_REPO_MB
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.\venv\Scripts\python.exe -m pytest backend/tests/test_disk_guard.py -v`

Expected: the 10 earlier tests pass; the 5 new ones FAIL with `AttributeError: module 'backend.app.disk_guard' has no attribute 'RepoTooLargeError'`.

- [ ] **Step 3: Write the implementation**

Add `import subprocess` and `import threading` to `backend/app/disk_guard.py`'s import block, then append:

```python
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

    # Any stale or partial directory from a previous attempt, cleared the way
    # that copes with git's read-only packfiles.
    if os.path.exists(dest):
        force_rmtree(dest)

    argv = command if command is not None else [*GIT_CLONE_BASE, url, dest]
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.\venv\Scripts\python.exe -m pytest backend/tests/test_disk_guard.py -v`

Expected: 15 passed.

- [ ] **Step 5: Wire it into the scan pipeline**

In `main.py`'s `run_scan_pipeline`, replace the raw clone in the `else:` branch (currently lines 261-265):

```python
            shutil.rmtree(repo_dir, ignore_errors=True)  # clear any stale/partial dir
            subprocess.run(
                ["git", "-c", "http.postBuffer=524288000", "clone",
                 "--single-branch", repo_url, repo_dir],
                check=True, timeout=300,
            )
```

with:

```python
            # clone_with_limit clears any stale/partial dir itself, using the
            # rmtree that copes with git's read-only packfiles — the plain
            # ignore_errors=True call this replaces could leave the directory
            # behind and make the clone fail with exit 128.
            disk_guard.clone_with_limit(repo_url, repo_dir, timeout=300)
```

- [ ] **Step 6: Document the variable**

Add to the disk-ceilings block in `.env.example` created in Task 2:

```
# Ceiling in MB on a single cloned repository. A clone growing past this is
# killed mid-flight and the partial tree deleted; the scan fails with a clear
# error. The 300s clone timeout is not a size limit — a fast link moves many
# gigabytes well inside it.
# MAX_REPO_MB=1024
```

- [ ] **Step 7: Run the full suite and the gate**

Run: `.\venv\Scripts\python.exe -m pytest backend/tests/ -q`

Expected: 303 passed, 0 failed.

Run: `.\venv\Scripts\python.exe backend/benchmark/run_benchmark.py --gate`

Expected: exit 0.

- [ ] **Step 8: Commit**

```bash
git add backend/app/disk_guard.py backend/tests/test_disk_guard.py main.py .env.example
git commit -F - <<'EOF'
Kill a clone that grows past MAX_REPO_MB

Nothing bounded the size of a scanned repository. The 300s clone timeout
was the only limit and it is not a size limit: a fast link moves many
gigabytes well inside 300 seconds, and the disk is gone before the
timeout would fire.

git has no native size limit, so a daemon thread polls the destination
while git runs and kills the process on breach, deleting the partial
tree. A post-clone check covers a repo that finishes between two polls.

Polling rather than a pre-clone provider API query: an API check only
covers hosts with a size endpoint, adds a round-trip to the scan path,
and a self-hosted host bypasses it. Post-clone alone would bound the
cache but not the peak -- by then the disk already holds the repo.

The error surfaces through run_scan_pipeline's existing handler, so the
UI renders it with no frontend change.
EOF
```

---

### Task 4: JSON logging

**Files:**
- Create: `backend/app/observability.py`
- Create: `backend/tests/test_observability.py`
- Modify: `main.py` (lifespan + `run_scan_pipeline`), `backend/app/services/celery_app.py:61`, `backend/app/services/retriever_service.py`
- Modify: `.env.example`, `backend/Dockerfile`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `configure_logging(force: bool = False) -> logging.Logger` — idempotent; returns the root logger.
  - `get_logger(name: str) -> logging.Logger`
  - `scan_context(scan_id: str)` — a context manager binding `scan_id` for the duration.
  - `current_scan_id() -> str | None`
  - `class JsonFormatter(logging.Formatter)`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_observability.py`:

```python
"""
Structured logging and error reporting (Phase E — ops hardening).

Before this module the project had zero logging: no getLogger, no
basicConfig, and 189 print() calls. A deployed container emitted
unstructured lines with no level, no timestamp, and no way to correlate two
lines belonging to the same scan.
"""

import json
import logging

import pytest

from backend.app import observability


@pytest.fixture(autouse=True)
def _clean_logging():
    """Each test gets a fresh root logger; handlers are global state."""
    yield
    observability.configure_logging(force=True)


def test_json_format_emits_parseable_records(monkeypatch, capsys):
    monkeypatch.setenv("LOG_FORMAT", "json")
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    observability.configure_logging(force=True)

    observability.get_logger("test.logger").info("scan started")

    payload = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    assert payload["message"] == "scan started"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "test.logger"
    assert payload["scan_id"] is None
    assert payload["timestamp"]


def test_scan_id_is_attached_from_the_contextvar(monkeypatch, capsys):
    monkeypatch.setenv("LOG_FORMAT", "json")
    observability.configure_logging(force=True)

    with observability.scan_context("scan-abc123"):
        observability.get_logger("test.logger").info("cloning")

    payload = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    assert payload["scan_id"] == "scan-abc123"


def test_scan_context_is_cleared_on_exit(monkeypatch):
    observability.configure_logging(force=True)
    with observability.scan_context("scan-abc123"):
        assert observability.current_scan_id() == "scan-abc123"
    assert observability.current_scan_id() is None


def test_scan_context_is_cleared_even_when_the_body_raises(monkeypatch):
    observability.configure_logging(force=True)
    with pytest.raises(ValueError):
        with observability.scan_context("scan-boom"):
            raise ValueError("pipeline blew up")
    assert observability.current_scan_id() is None


def test_configure_logging_is_idempotent(monkeypatch):
    """Calling twice must not double every log line."""
    monkeypatch.setenv("LOG_FORMAT", "json")
    observability.configure_logging(force=True)
    observability.configure_logging()
    observability.configure_logging()

    ours = [h for h in logging.getLogger().handlers
            if getattr(h, "_etproject", False)]
    assert len(ours) == 1


def test_text_format_is_the_default(monkeypatch, capsys):
    monkeypatch.delenv("LOG_FORMAT", raising=False)
    observability.configure_logging(force=True)

    observability.get_logger("test.logger").info("plain line")

    line = capsys.readouterr().err.strip().splitlines()[-1]
    with pytest.raises(json.JSONDecodeError):
        json.loads(line)
    assert "plain line" in line


def test_log_level_is_read_from_env(monkeypatch, capsys):
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    monkeypatch.setenv("LOG_FORMAT", "json")
    observability.configure_logging(force=True)

    observability.get_logger("test.logger").info("should not appear")
    observability.get_logger("test.logger").warning("should appear")

    lines = capsys.readouterr().err.strip().splitlines()
    messages = [json.loads(line)["message"] for line in lines if line]
    assert "should not appear" not in messages
    assert "should appear" in messages


def test_exception_info_is_included(monkeypatch, capsys):
    monkeypatch.setenv("LOG_FORMAT", "json")
    observability.configure_logging(force=True)

    try:
        raise RuntimeError("clone failed")
    except RuntimeError:
        observability.get_logger("test.logger").exception("scan errored")

    payload = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    assert "RuntimeError: clone failed" in payload["exc_info"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.\venv\Scripts\python.exe -m pytest backend/tests/test_observability.py -v`

Expected: FAIL at collection with `ImportError: cannot import name 'observability'`.

- [ ] **Step 3: Write the implementation**

Create `backend/app/observability.py`:

```python
# ==========================================================
# File: observability.py
# Purpose: Structured logging and error reporting (Phase E — ops hardening).
# ==========================================================
#
# Before this module the project had no logging at all: zero getLogger, zero
# basicConfig, 189 print() calls. A container emitted unstructured lines with
# no level, no timestamp, and nothing tying two lines to the same scan.
#
# ENV (all read at CALL time, never at import time — the api_guard.py idiom):
#   LOG_LEVEL   Root level. Default INFO.
#   LOG_FORMAT  "text" or "json". Default "text", so start.bat's two console
#               windows stay readable in local development. The Dockerfile
#               sets LOG_FORMAT=json, so containers are structured by default
#               without an operator needing to know the variable exists.

import contextlib
import contextvars
import json
import logging
import os
import sys
from datetime import datetime, timezone

DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_LOG_FORMAT = "text"

TEXT_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"

# The unit of work worth correlating. A contextvar rather than an argument
# threaded through every call because the scan path crosses many modules that
# have no other reason to know logging exists, and because it behaves the same
# whether Celery is eager (in-process) or dispatching to a worker.
_scan_id = contextvars.ContextVar("etproject_scan_id", default=None)


def current_scan_id():
    return _scan_id.get()


@contextlib.contextmanager
def scan_context(scan_id):
    """Bind scan_id to every log record emitted inside this block."""
    token = _scan_id.set(scan_id)
    try:
        yield
    finally:
        _scan_id.reset(token)


class JsonFormatter(logging.Formatter):
    """One JSON object per line, with a stable schema.

    scan_id is always present, null when no scan is in context: a log
    aggregator gains more from a stable schema than from a few saved bytes.
    """

    def format(self, record):
        payload = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "scan_id": current_scan_id(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def _log_level():
    name = os.getenv("LOG_LEVEL", DEFAULT_LOG_LEVEL).strip().upper()
    return getattr(logging, name, logging.INFO)


def _log_format():
    return os.getenv("LOG_FORMAT", DEFAULT_LOG_FORMAT).strip().lower()


def configure_logging(force=False):
    """Attach one stderr handler to the root logger. Idempotent.

    Handlers are global state and a second one doubles every line, so ours is
    tagged and replaced rather than appended. Configures the ROOT logger on
    purpose: uvicorn's and celery's records are exactly the ops signal a
    deployment needs, and they propagate to root.
    """
    root = logging.getLogger()
    existing = [h for h in root.handlers if getattr(h, "_etproject", False)]

    if existing and not force:
        return root

    for handler in existing:
        root.removeHandler(handler)

    handler = logging.StreamHandler(stream=sys.stderr)
    handler._etproject = True
    if _log_format() == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(TEXT_FORMAT))

    root.addHandler(handler)
    root.setLevel(_log_level())
    return root


def get_logger(name):
    return logging.getLogger(name)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.\venv\Scripts\python.exe -m pytest backend/tests/test_observability.py -v`

Expected: 8 passed.

- [ ] **Step 5: Wire it into both entrypoints**

In `main.py`, add to the import block near line 24:

```python
from backend.app import observability
```

Immediately after that import block and before `app = FastAPI(...)` (around line 54), add:

```python
# Structured logging is configured before anything else so startup records
# are formatted too.
observability.configure_logging()
logger = observability.get_logger("etproject.api")
```

In `backend/app/services/celery_app.py`, inside `_recover_on_worker_ready` (line 62), add as the first statement of the function body, after the docstring:

```python
    from backend.app import observability
    observability.configure_logging()
```

The import is function-local here deliberately: `celery_app` is imported by `main`, and a module-scope import would create a cycle through `main`'s own configure call.

- [ ] **Step 6: Bind the scan id and convert the pipeline's prints**

In `main.py`, wrap the body of `run_scan_pipeline` in the scan context. Change the signature line and what follows it from:

```python
def run_scan_pipeline(scan_id: str, repo_url: str, explanation_depth: str = "senior"):

    os.makedirs(CLONE_CACHE, exist_ok=True)
```

to:

```python
def run_scan_pipeline(scan_id: str, repo_url: str, explanation_depth: str = "senior"):

    with observability.scan_context(scan_id):
        _run_scan_pipeline(scan_id, repo_url, explanation_depth)


def _run_scan_pipeline(scan_id: str, repo_url: str, explanation_depth: str):

    os.makedirs(CLONE_CACHE, exist_ok=True)
```

Indentation of the original body is unchanged — it moves wholesale into `_run_scan_pipeline`. Splitting rather than indenting the whole body inside a `with` keeps the diff readable and the function's existing structure intact.

In the same file's `except Exception as e:` handler at the end of the pipeline, add a log line before the existing `complete_scan` call:

```python
        logger.exception("scan failed: %s", e)
```

- [ ] **Step 7: Convert the retriever warnings**

In `backend/app/services/retriever_service.py`, add after the existing imports:

```python
from backend.app.observability import get_logger

logger = get_logger("etproject.retriever")
```

Replace the three `print(...)` calls with the equivalent logger calls:

```python
            logger.warning("failed to load embedding model: %s", e)
```

```python
                logger.warning("failed to load FAISS index: %s", e)
```

```python
            logger.info("FAISS index not found; using fallback retrieval")
```

The third is `info`, not `warning`: no index shipping is the normal, expected state in every deployed configuration, and logging the expected case at warning level is how a warning stops meaning anything.

- [ ] **Step 8: Set the container default and document the variables**

In `backend/Dockerfile`, add `LOG_FORMAT=json` to the existing `ENV` block:

```dockerfile
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    LOG_FORMAT=json
```

Append to `.env.example`:

```
# ----------------------------------------------------------
# Logging (backend/app/observability.py)
# ----------------------------------------------------------

# DEBUG | INFO | WARNING | ERROR. Applies to the root logger, so uvicorn and
# celery records are covered too.
# LOG_LEVEL=INFO

# text | json. Defaults to text so local console output stays readable; the
# Dockerfile sets json, so containers are structured without extra config.
# LOG_FORMAT=text
```

- [ ] **Step 9: Run the full suite and the gate**

Run: `.\venv\Scripts\python.exe -m pytest backend/tests/ -q`

Expected: 311 passed, 0 failed.

Run: `.\venv\Scripts\python.exe backend/benchmark/run_benchmark.py --gate`

Expected: exit 0.

- [ ] **Step 10: Commit**

```bash
git add backend/app/observability.py backend/tests/test_observability.py main.py backend/app/services/celery_app.py backend/app/services/retriever_service.py backend/Dockerfile .env.example
git commit -F - <<'EOF'
Add structured logging with per-scan correlation

The project had no logging: zero getLogger, zero basicConfig, and 189
print() calls. A deployed container emitted unstructured lines with no
level, no timestamp, and no way to tie two lines to the same scan.

Adds a JSON formatter behind LOG_FORMAT, defaulting to text so local
console output stays readable while the Dockerfile sets json. Configures
the root logger on purpose, so uvicorn and celery records are covered.

scan_id rides a contextvar bound at the top of run_scan_pipeline rather
than an argument threaded through every module, because the scan path
crosses many modules with no other reason to know logging exists, and a
contextvar behaves the same whether Celery is eager or dispatching. The
field is always present, null when no scan is in context -- a stable
schema is worth more to an aggregator than a few saved bytes.

Converts the ops surfaces only. report_generator's rich tables stay as
they are: that is CLI presentation for a human terminal, and routing it
through a JSON formatter would destroy it while improving nothing. The
"FAISS index not found" line drops to info because in every shipped
config that is the expected state, and warning-level expected cases are
how warnings stop meaning anything.
EOF
```

---

### Task 5: Sentry, off by default

**Files:**
- Modify: `backend/app/observability.py` (add `init_sentry`)
- Modify: `backend/tests/test_observability.py` (add Sentry tests)
- Modify: `main.py`, `backend/app/services/celery_app.py` (call it)
- Modify: `requirements.txt`, `.env.example`

**Interfaces:**
- Consumes: `configure_logging` from Task 4.
- Produces: `init_sentry() -> bool` — `True` when the SDK was initialized, `False` when disabled or unavailable.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_observability.py`:

```python
def test_sentry_is_disabled_without_a_dsn(monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    calls = []
    monkeypatch.setattr("sentry_sdk.init", lambda **kw: calls.append(kw))

    assert observability.init_sentry() is False
    assert calls == []


def test_sentry_is_disabled_by_an_empty_dsn(monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "   ")
    calls = []
    monkeypatch.setattr("sentry_sdk.init", lambda **kw: calls.append(kw))

    assert observability.init_sentry() is False
    assert calls == []


def test_sentry_initializes_when_a_dsn_is_set(monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "https://key@example.invalid/1")
    monkeypatch.setenv("SENTRY_ENVIRONMENT", "production")
    calls = []
    monkeypatch.setattr("sentry_sdk.init", lambda **kw: calls.append(kw))

    assert observability.init_sentry() is True
    assert len(calls) == 1
    assert calls[0]["dsn"] == "https://key@example.invalid/1"
    assert calls[0]["environment"] == "production"
    assert calls[0]["traces_sample_rate"] == 0.0


def test_sentry_environment_defaults_to_development(monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "https://key@example.invalid/1")
    monkeypatch.delenv("SENTRY_ENVIRONMENT", raising=False)
    calls = []
    monkeypatch.setattr("sentry_sdk.init", lambda **kw: calls.append(kw))

    observability.init_sentry()

    assert calls[0]["environment"] == "development"


def test_sentry_traces_sample_rate_is_read_from_env(monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "https://key@example.invalid/1")
    monkeypatch.setenv("SENTRY_TRACES_SAMPLE_RATE", "0.25")
    calls = []
    monkeypatch.setattr("sentry_sdk.init", lambda **kw: calls.append(kw))

    observability.init_sentry()

    assert calls[0]["traces_sample_rate"] == 0.25
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.\venv\Scripts\python.exe -m pytest backend/tests/test_observability.py -v`

Expected: the 8 Task-4 tests pass; the 5 new ones FAIL with `AttributeError: module 'backend.app.observability' has no attribute 'init_sentry'`.

- [ ] **Step 3: Add the dependency**

Append to the "Environment" section of `requirements.txt`:

```
# Error reporting. Inert unless SENTRY_DSN is set — see backend/app/observability.py.
sentry-sdk
```

Install it into the venv so the tests can patch `sentry_sdk.init`:

Run: `.\venv\Scripts\python.exe -m pip install sentry-sdk`

**Regenerate `requirements.lock` in this task too** — do not defer it to Task 6.
The five tests below patch `sentry_sdk.init`, which requires `sentry_sdk` to be
importable. `init_sentry()` imports lazily inside the DSN branch, so the
application would survive a stale lock, but a CI run on this commit installs
`requirements.lock`, finds no `sentry-sdk`, and all five error. Every commit
stays independently green:

```
.\venv\Scripts\python.exe -m pip install pip-tools
.\venv\Scripts\python.exe -m piptools compile --output-file=requirements.lock requirements.txt
```

Confirm it landed:

```
grep -i "^sentry-sdk" requirements.lock
```

Expected: one matching line. Task 6 regenerates this lock again after removing
the ML block; that second run is expected, not redundant work to skip.

- [ ] **Step 4: Write the implementation**

Append to `backend/app/observability.py`:

```python
# ----------------------------------------------------------
# Sentry
# ----------------------------------------------------------
#
# ENV (read at CALL time):
#   SENTRY_DSN                  Unset or empty => Sentry is entirely disabled.
#   SENTRY_ENVIRONMENT          Tag on reported events. Default "development".
#   SENTRY_TRACES_SAMPLE_RATE   Default 0.0 — tracing costs money and nobody
#                               asked for it.
#
# Disabled-by-default makes "no data leaves the machine" the default posture,
# and makes the feature verifiable locally: the disabled path is the one the
# suite and every developer machine actually exercise.

DEFAULT_SENTRY_ENVIRONMENT = "development"


def _traces_sample_rate():
    raw = os.getenv("SENTRY_TRACES_SAMPLE_RATE", "").strip()
    if not raw:
        return 0.0
    try:
        return float(raw)
    except ValueError:
        return 0.0


def init_sentry():
    """Initialize Sentry if SENTRY_DSN is set. Returns whether it was.

    Call AFTER configure_logging: Sentry's logging integration attaches to
    existing handlers, so initializing first would silently miss them.
    """
    dsn = os.getenv("SENTRY_DSN", "").strip()
    if not dsn:
        return False

    try:
        import sentry_sdk
    except ImportError:
        get_logger("etproject.observability").warning(
            "SENTRY_DSN is set but sentry-sdk is not installed; "
            "error reporting is off"
        )
        return False

    sentry_sdk.init(
        dsn=dsn,
        environment=os.getenv(
            "SENTRY_ENVIRONMENT", DEFAULT_SENTRY_ENVIRONMENT
        ).strip() or DEFAULT_SENTRY_ENVIRONMENT,
        traces_sample_rate=_traces_sample_rate(),
    )
    return True
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.\venv\Scripts\python.exe -m pytest backend/tests/test_observability.py -v`

Expected: 13 passed.

- [ ] **Step 6: Call it from both entrypoints**

In `main.py`, extend the startup block added in Task 4:

```python
observability.configure_logging()
observability.init_sentry()
logger = observability.get_logger("etproject.api")
```

In `backend/app/services/celery_app.py`'s `_recover_on_worker_ready`, extend the block added in Task 4:

```python
    from backend.app import observability
    observability.configure_logging()
    observability.init_sentry()
```

- [ ] **Step 7: Document the variables**

Append to `.env.example`:

```
# ----------------------------------------------------------
# Error reporting (backend/app/observability.py)
# ----------------------------------------------------------

# Leave unset and Sentry is entirely disabled — no data leaves the machine.
# Set it to turn error reporting on; nothing else is required.
# SENTRY_DSN=

# Tag applied to reported events.
# SENTRY_ENVIRONMENT=development

# Performance tracing sample rate. 0.0 = tracing off.
# SENTRY_TRACES_SAMPLE_RATE=0.0
```

- [ ] **Step 8: Run the full suite**

Run: `.\venv\Scripts\python.exe -m pytest backend/tests/ -q`

Expected: 316 passed, 0 failed.

- [ ] **Step 9: Commit**

```bash
git add backend/app/observability.py backend/tests/test_observability.py main.py backend/app/services/celery_app.py requirements.txt requirements.lock .env.example
git commit -F - <<'EOF'
Report errors to Sentry when a DSN is configured

init_sentry returns immediately unless SENTRY_DSN is set, so the default
posture is that no data leaves the machine and the disabled path is the
one the suite and every developer machine actually exercise. Turning it
on at deploy needs nothing but the env var.

Called after configure_logging in both entrypoints, and the order is
load-bearing: Sentry's logging integration attaches to existing
handlers, so initializing first would silently miss them.

Tracing defaults to 0.0. sentry-sdk is pure-Python and small, so it does
not undercut the image-slimming work.

No end-to-end verification: there is no DSN on this machine and the
tests mock sentry_sdk.init rather than emitting a real event.
EOF
```

---

### Task 6: Image slimming

The payoff task. `rag/faiss_index/` is gitignored, so no FAISS index is ever present in a container and `CodeRetriever.retrieve()` always takes its no-index fallback. `ENABLE_CODEBERT` defaults false, so the CodeBERT branch never runs. Yet module-scope imports drag torch in regardless, and the image pays gigabytes for code that cannot execute.

**Files:**
- Create: `requirements-ml.txt`, `requirements-ml.lock`
- Modify: `requirements.txt`, `requirements.lock`, `backend/Dockerfile`
- Modify: `backend/app/services/retriever_service.py:6,11`, `backend/app/services/llm_service.py:12,83`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: no new callable API. The contract preserved is `CodeRetriever.retrieve()` returning a list under all conditions, and `get_embedding_model()` returning `None` when the model is unavailable.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_retrieval.py`:

```python
def test_retriever_degrades_when_ml_deps_are_absent(monkeypatch):
    """A base install has no sentence-transformers; import must not explode.

    Phase E moved the ML stack to an optional requirements file. The scan path
    imports this module unconditionally, so a missing dependency has to fold
    into the existing graceful-degradation path rather than raising at import.
    """
    import builtins

    real_import = builtins.__import__

    def _no_ml(name, *args, **kwargs):
        if name.startswith("sentence_transformers") or name == "faiss":
            raise ImportError(f"No module named {name!r}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _no_ml)

    import backend.app.services.retriever_service as rs
    monkeypatch.setattr(rs, "_embedding_model", None)

    retriever = rs.CodeRetriever()
    assert retriever.model is None
    assert isinstance(retriever.retrieve("anything"), list)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.\venv\Scripts\python.exe -m pytest backend/tests/test_retrieval.py -v`

Expected: the 4 existing tests pass; the new one FAILS — currently the imports are at module scope, so patching `__import__` cannot affect an already-imported module and `retriever.model` is a real `SentenceTransformer`, not `None`.

- [ ] **Step 3: Make the retriever's ML imports lazy**

In `backend/app/services/retriever_service.py`, delete these two module-scope imports:

```python
import faiss
```

```python
from sentence_transformers import SentenceTransformer
```

In `get_embedding_model()`, replace the existing body of the `if _embedding_model is None:` branch:

```python
        try:
            _embedding_model = SentenceTransformer(MODEL_NAME)
        except Exception as e:
            logger.warning("failed to load embedding model: %s", e)
            _embedding_model = None
```

with:

```python
        # Imported here, not at module scope: Phase E moved the ML stack to an
        # optional requirements file, and the scan path imports this module
        # unconditionally. ImportError folds into the same degradation path as
        # a model that fails to load — retrieve() already handles model=None.
        try:
            from sentence_transformers import SentenceTransformer
            _embedding_model = SentenceTransformer(MODEL_NAME)
        except Exception as e:
            logger.warning("embedding model unavailable: %s", e)
            _embedding_model = None
```

`ImportError` is a subclass of `Exception`, so the existing broad handler
already covers a missing dependency — only the import's position and the log
wording change here.

In `CodeRetriever.__init__`, replace the FAISS load block:

```python
            try:
                self.index = faiss.read_index(str(INDEX_PATH))

                with open(METADATA_PATH, "rb") as f:
                    self.metadata = pickle.load(f)

            except Exception as e:
                logger.warning("failed to load FAISS index: %s", e)
```

with:

```python
            try:
                import faiss

                self.index = faiss.read_index(str(INDEX_PATH))

                with open(METADATA_PATH, "rb") as f:
                    self.metadata = pickle.load(f)

            except Exception as e:
                logger.warning("FAISS index unavailable: %s", e)
```

`ImportError` is a subclass of `Exception`, so the existing handler covers it.

- [ ] **Step 4: Make the llm_service import lazy**

In `backend/app/services/llm_service.py`, delete the module-scope import at line 12:

```python
from backend.app.services.retriever_service import CodeRetriever
```

At the instantiation site (line 83), change:

```python
        _retriever = CodeRetriever()
```

to:

```python
        # Local import: retriever_service reaches for the optional ML stack,
        # and importing it at module scope would make every scan path require
        # dependencies that no shipped configuration can actually use.
        from backend.app.services.retriever_service import CodeRetriever

        _retriever = CodeRetriever()
```

- [ ] **Step 5: Run the retrieval tests**

Run: `.\venv\Scripts\python.exe -m pytest backend/tests/test_retrieval.py -v`

Expected: 5 passed.

- [ ] **Step 6: Split the requirements files**

Create `requirements-ml.txt`:

```
--extra-index-url https://download.pytorch.org/whl/cpu

# ==========================================================
# Optional ML stack (Phase E)
# ==========================================================
# NOT installed in the production image. Nothing in a shipped configuration
# can reach this code: rag/faiss_index/ is gitignored so CodeRetriever always
# takes its no-index fallback, and ENABLE_CODEBERT defaults to false.
#
# Install alongside the base requirements only for a deployment that actually
# wants CodeBERT scoring or FAISS retrieval, and that ships an index:
#     pip install -r requirements.lock -r requirements-ml.lock
#
# There is no pyproject.toml in this repo, so this is a separate requirements
# file rather than a setuptools [ml] extra.

torch
transformers
sentence-transformers
faiss-cpu
```

In `requirements.txt`, delete the first line:

```
--extra-index-url https://download.pytorch.org/whl/cpu
```

and delete the entire "Core AI / ML" block:

```
# ==========================================================
# Core AI / ML
# ==========================================================
torch
transformers
sentence-transformers
```

and delete `faiss-cpu` from the "Vector Search / RAG" block, leaving `numpy` and `scikit-learn`. Replace the emptied Core AI/ML block with a pointer:

```
# ==========================================================
# Core AI / ML — moved to requirements-ml.txt (Phase E)
# ==========================================================
# torch, transformers, sentence-transformers and faiss-cpu are optional and
# are NOT in the production image. See requirements-ml.txt for why.
```

- [ ] **Step 7: Regenerate both locks**

pip-compile, not `pip freeze` — a freeze captures the dev-venv superset and produced a wrong 131-package lock once already in Phase B.

Run:

```
.\venv\Scripts\python.exe -m pip install pip-tools
.\venv\Scripts\python.exe -m piptools compile --output-file=requirements.lock requirements.txt
.\venv\Scripts\python.exe -m piptools compile --output-file=requirements-ml.lock requirements-ml.txt
```

Then confirm the base lock is actually clean:

```
grep -iE "^(torch|transformers|sentence-transformers|faiss|nvidia)" requirements.lock
```

Expected: **no output.** If anything matches, a base dependency is pulling ML transitively and the split is incomplete — stop and investigate rather than editing the lock by hand.

- [ ] **Step 8: Point the Dockerfile at the base lock only**

`backend/Dockerfile` already installs `requirements.lock`, so no line changes. Update the stale comment above it, which claims the build is necessarily huge:

```dockerfile
# Installs from requirements.lock, NOT requirements.txt: the loose file would
# let a transitive release change what ships between two builds of the same
# commit.
#
# Phase E: the ML stack (torch, transformers, sentence-transformers, faiss)
# moved to requirements-ml.lock and is deliberately NOT installed here. No
# shipped configuration can reach it — rag/faiss_index/ is gitignored so
# retrieval always takes its fallback, and ENABLE_CODEBERT defaults false.
# A deployment that genuinely wants it adds a second -r for the ml lock.
```

- [ ] **Step 9: Full verification**

Run: `.\venv\Scripts\python.exe -m pytest backend/tests/ -q`

Expected: 317 passed, 0 failed.

Run: `.\venv\Scripts\python.exe backend/benchmark/run_benchmark.py --gate`

Expected: exit 0.

Run: `cd frontend; npx tsc -b; npm run build`

Expected: both exit 0. (Unchanged by this task — run them to confirm nothing regressed.)

**Note:** the slimmed image cannot be built or booted here — Docker is not installed on this machine. Report the image as CI-verified once the branch pushes; never claim a local build.

- [ ] **Step 10: Commit**

```bash
git add requirements.txt requirements.lock requirements-ml.txt requirements-ml.lock backend/Dockerfile backend/app/services/retriever_service.py backend/app/services/llm_service.py backend/tests/test_retrieval.py
git commit -F - <<'EOF'
Move the ML stack out of the production image

torch, transformers, sentence-transformers and faiss-cpu cost the image
gigabytes for code no shipped configuration can execute. rag/faiss_index
is gitignored, so CodeRetriever always takes its no-index fallback and
returns mock_result; ENABLE_CODEBERT defaults false, so the CodeBERT
branch never runs. Module-scope imports pulled all of it in regardless.

They move to requirements-ml.txt with their own lock. The roadmap called
this an optional [ml] extra, but there is no pyproject.toml or setup.py
for an extra to attach to, so a second requirements pair delivers the
same outcome using the convention already here.

Two imports had to go lazy or a base install would fail at import rather
than at use: retriever_service's faiss and sentence_transformers, and
llm_service's module-scope CodeRetriever. Both fold ImportError into the
existing graceful-degradation path, which is what lets test_retrieval's
existing cases keep passing untouched -- they already assert exactly
that contract.

Locks regenerated with pip-compile, not pip freeze; a freeze captured
the dev-venv superset once already.

The image itself is not verified here: Docker is not installed on this
machine, so build and boot are left to CI.
EOF
```

---

### Task 7: Operations documentation and final verification

**Files:**
- Modify: `DEPLOYMENT.md`

**Interfaces:**
- Consumes: every variable and behaviour from Tasks 1-6.
- Produces: nothing consumed by code.

- [ ] **Step 1: Add the operations section**

Append to `DEPLOYMENT.md`:

```markdown
## Operations (Phase E)

### Disk ceilings

Two caches grow as repositories are scanned: a full git clone per distinct
repository URL, and a small JSON prior per repository used for incremental
re-analysis. Both are bounded.

| Variable | Default | Effect |
|---|---|---|
| `MAX_CACHE_MB` | `5120` | Combined ceiling. When exceeded, least-recently-scanned repositories are evicted — clone and prior together — at the start of the next scan. |
| `MAX_REPO_MB` | `1024` | Ceiling on a single repository. A clone growing past it is killed mid-flight, the partial tree is deleted, and the scan fails with a clear error. |

Eviction runs inline at the start of a scan, not on a timer. An idle
deployment therefore reclaims nothing until the next scan arrives — which is
also when it next needs the space. If a host is tight on disk, lower
`MAX_CACHE_MB` rather than adding a cron job.

`MAX_REPO_MB` is the guard against a hostile or accidental giant repository.
The clone timeout is not a substitute: a fast link moves many gigabytes well
inside 300 seconds.

### Logs

Containers emit one JSON object per line (`LOG_FORMAT=json` is set in the
Dockerfile). Every record carries `timestamp`, `level`, `logger`, `message`,
and `scan_id` — `null` outside a scan, so filtering a whole scan out of an
aggregator is one query. Set `LOG_LEVEL=DEBUG` to raise verbosity; the root
logger is configured, so uvicorn and celery records are included.

Set `LOG_FORMAT=text` for human-readable output when tailing a container by
hand.

### Error reporting

Sentry is off unless `SENTRY_DSN` is set. To turn it on, set the DSN and
optionally `SENTRY_ENVIRONMENT` (default `development`); restart the API and
the worker. `SENTRY_TRACES_SAMPLE_RATE` defaults to `0.0` — raise it only if
you want performance tracing and accept the cost.

With no DSN configured, nothing is sent anywhere.

### Optional ML stack

The production image does **not** install torch, transformers,
sentence-transformers, or faiss-cpu. No shipped configuration can reach that
code: no FAISS index is built into the image, so retrieval takes its fallback
path, and `ENABLE_CODEBERT` defaults to `false`.

A deployment that genuinely wants CodeBERT scoring or FAISS retrieval needs
both locks and an index built into the image:

```
pip install -r requirements.lock -r requirements-ml.lock
```

Without the extra installed, the retrieval and CodeBERT paths degrade quietly
and log at warning level; they do not fail the scan.
```

- [ ] **Step 2: Full verification sweep**

Run all four, and record the actual output of each — no completion claim without it:

```
.\venv\Scripts\python.exe -m pytest backend/tests/ -q
.\venv\Scripts\python.exe backend/benchmark/run_benchmark.py --gate
cd frontend; npx tsc -b
cd frontend; npm run build
```

Expected: 317 passed / 0 failed; gate exit 0; `tsc -b` exit 0; build exit 0.

- [ ] **Step 3: Commit**

```bash
git add DEPLOYMENT.md
git commit -F - <<'EOF'
Document the Phase E operational surface

Covers the two disk ceilings and why eviction is inline rather than
scheduled, the JSON log schema and the scan_id field that makes a whole
scan filterable in an aggregator, how to turn Sentry on, and how to
install the optional ML stack for a deployment that ships a FAISS index.
EOF
```

- [ ] **Step 4: Push and confirm CI**

```bash
git push -u origin phase-e/ops-hardening
gh run list --branch phase-e/ops-hardening --limit 2
```

CI is the first place the slimmed image and the regenerated locks are
genuinely exercised — the backend job installs `requirements.lock` on a Linux
runner. A base-lock install that fails there means the ML split missed a
transitive dependency.

Do not report the image as verified until this run is green.

---

## Self-Review

**Spec coverage:**

| Spec section | Task |
|---|---|
| Component 1 — JSON logging | Task 4 |
| Component 2 — Sentry | Task 5 |
| Component 3 — LRU eviction | Task 2 |
| Component 4 — clone watchdog | Task 3 |
| Component 4 — shared `force_rmtree` | Task 1 |
| Component 5 — image slimming | Task 6 |
| Documentation (`.env.example`) | Tasks 2, 3, 4, 5 (each var with its feature) |
| Documentation (`DEPLOYMENT.md`) | Task 7 |
| Testing section | Tasks 1-6, test-first in every case |

No spec requirement is unassigned.

**Deviation from the spec's sequencing, deliberate:** the spec lists five
commits with observability as one; this plan splits it into Task 4 (logging)
and Task 5 (Sentry), and adds Task 7 for `DEPLOYMENT.md`. The spec itself
phrases that commit as "observability (logging, then Sentry)", so the split
follows its intent — and a reviewer could sensibly accept the logging work
while rejecting the Sentry dependency, which is exactly the boundary a task
should fall on.

**Type consistency:** `force_rmtree`, `dir_size_bytes`, `max_cache_mb`,
`max_repo_mb`, `evict_caches`, `clone_with_limit`, `RepoTooLargeError`,
`configure_logging`, `get_logger`, `scan_context`, `current_scan_id`,
`init_sentry` — each defined once, in the task that introduces it, and used
under the same name everywhere after.

**Expected test counts, cumulative from the 288 baseline:** Task 1 → 291,
Task 2 → 298, Task 3 → 303, Task 4 → 311, Task 5 → 316, Task 6 → 317. If a
task's count comes in different from this, something else changed and it
needs explaining before moving on.
