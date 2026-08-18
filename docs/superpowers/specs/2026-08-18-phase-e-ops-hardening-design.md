# Phase E — Ops Hardening

**Date:** 2026-08-18
**Status:** Approved, ready for implementation planning
**Branch:** `phase-e/ops-hardening`
**Baseline:** `ac23d8e` on `main` (Phase D merge, CI green, runs 32042777569 + 32042866213)

## Context

The 2026-08 audit graded this project 6.7/10 across phases A–G. Phases A
(security hardening), B (CI + release), C (detector precision), and D (frontend
hardening) are merged to `main` and green. Phase E is the operational layer:
the things that decide whether a deployment survives its second month rather
than its first hour.

Four facts about the current tree, all verified on `ac23d8e`, define the work.

**There is no logging.** Zero `logging.getLogger`, zero `basicConfig`, and
**189 `print()` calls** across `backend/`, `rag/`, and `main.py`. "Add JSON
logging" is therefore not a formatting change to an existing logging setup —
it is building the first one. A deployed container today emits unstructured
lines to stdout with no level, no timestamp, and no way to correlate two lines
belonging to the same scan.

**Two caches grow without bound.** `main.py:225` keeps a persistent full clone
per distinct `repo_url` under `CLONE_CACHE`, deliberately not shallow so a
re-scan can diff history. `backend/app/services/incremental.py:28` keeps a
parallel per-repo prior store under `CACHE_DIR`. Neither is ever evicted. This
is a tracked deferral from Chunk 5, accepted at the time on the explicit
condition that it be fixed when real deployment work began. Phase E is that
work.

**Nothing bounds the size of a scanned repository.** `main.py:263` clones
whatever URL passes the `api_guard` host allowlist, with a 300-second timeout
as the only limit. A timeout is not a size limit: a fast link can pull many
gigabytes well inside 300 seconds, and the disk is gone before the timeout
would ever fire.

**The ML stack is dead weight in every configuration that currently ships.**
`rag/faiss_index/` is gitignored (`.gitignore:57`), so no FAISS index is ever
present in a container; `CodeRetriever.retrieve()` consequently takes its
no-index fallback and returns `["mock_result"]`. `ENABLE_CODEBERT` defaults to
`false` (`llm_service.py:29`), so the CodeBERT branch never executes. Yet
`llm_service.py:12` imports `CodeRetriever` at module scope, and
`retriever_service.py:6,11` import `faiss` and `sentence_transformers` at
module scope, so importing the scan path drags in torch unconditionally. The
image pays multiple gigabytes for code that cannot run.

## Goals

1. Bound disk: no cache may grow without limit, and no single repository may
   exhaust the volume mid-clone.
2. Make the running system legible: structured logs correlated by scan, and
   errors reportable to Sentry when an operator opts in.
3. Stop shipping unused multi-gigabyte dependencies in the production image.

## Non-goals

- Booting or measuring the slimmed image. Docker is not installed on this
  machine. Image build and boot are **CI-verified or user-verified only**; this
  phase will not claim them.
- Periodic background eviction. That needs Celery beat and a fourth compose
  service, and the beat path cannot run in eager mode — it would be the one
  piece of Phase E with no local verification. Eviction runs inline instead.
- An HTTP request-id middleware. `scan_id` is the unit of work worth
  correlating; a request id would be invented scope.
- Deleting the retrieval or CodeBERT features. They stop shipping by default
  but remain installable and working.
- Distributed-tracing spans. `SENTRY_TRACES_SAMPLE_RATE` defaults to `0.0`.

## Correction to the roadmap's wording

The roadmap phrases image slimming as "torch → optional `[ml]` extra". There is
no `pyproject.toml`, `setup.py`, or `setup.cfg` in this repository — packaging
is requirements-file based, so there is no distribution metadata for a
setuptools extra to attach to. Delivering a literal `[ml]` extra would mean
introducing packaging machinery and rewiring CI and the Dockerfile around it.

**Decision:** use `requirements-ml.txt` + `requirements-ml.lock` alongside the
existing `requirements.txt` + `requirements.lock` pair. Same outcome — the base
install contains no torch — using the convention already in the repo.

## Architecture

Two new modules, each holding one boundary in one readable file. This follows
the principle `api_guard.py` states for itself: the controls are "kept together
so the whole trust boundary is readable in one file rather than scattered
through route bodies."

- **`backend/app/observability.py`** — JSON logging and Sentry initialization.
- **`backend/app/disk_guard.py`** — cache eviction, the clone size watchdog,
  and the shared filesystem helpers both need.

Rejected alternatives: a `backend/app/ops/` package of four modules (splits
roughly forty lines of shared disk helpers across files for no gain), and
spreading the work into existing modules (eviction into `incremental.py`, the
guard inline in `main.py`), which would leave the disk ceiling with no single
place a reader can find it and would grow `main.py` further.

**All environment variables are read at call time, never at import time.** This
is the idiom `api_guard.py` documents and the reason it is testable:
monkeypatching `os.environ` works without reloading `main`. `celery_app.py`
reads its configuration at import time and is correspondingly painful to test;
that pattern is not to be copied.

## Component 1 — `observability.py`: JSON logging

### Configuration

| Variable | Default | Meaning |
|---|---|---|
| `LOG_LEVEL` | `INFO` | Root level for the application logger. |
| `LOG_FORMAT` | `text` | `text` or `json`. |

`LOG_FORMAT` defaults to `text` so `start.bat`'s two console windows stay
readable during local development. The Dockerfile sets `LOG_FORMAT=json`, so
every container gets structured output without an operator having to know the
variable exists.

### Behaviour

`configure_logging()` is idempotent — calling it twice must not attach a second
handler and double every line. It is called from two entrypoints:

- `main.py` at application startup.
- The Celery worker, via the `worker_ready` signal already present in
  `celery_app.py`.

The JSON formatter emits `timestamp`, `level`, `logger`, `message`, and
`scan_id`, plus a formatted `exc_info` when an exception is attached.

### Scan correlation

`scan_id` is carried in a `contextvars.ContextVar`, set at the top of
`run_scan_pipeline` and cleared when it returns. A contextvar rather than a
threaded-through argument because the scan path crosses many modules that have
no other reason to know about logging, and because it works unchanged whether
Celery is eager (in-process) or dispatching to a worker.

When no scan is in context the field is `null`, not absent — a stable schema is
worth more to a log aggregator than a few saved bytes.

### Conversion scope

Converted to logger calls: `main.py`'s scan pipeline, `celery_app.py` and
`tasks.py`, `api_guard.py`, the scan store, and the `[Retriever Warning]`
prints in `retriever_service.py`.

**Not converted:** `report_generator.py`'s `rich` tables and panels. That is
CLI presentation for a human terminal, not telemetry, and routing it through a
JSON formatter would destroy it while improving nothing.

The remaining `print()` calls in analysis modules and scripts are left alone.
This is a deliberate scope cut, not an oversight: converting all 189 would
sweep in CLI output and produce a diff far larger than the ops value it buys.

## Component 2 — `observability.py`: Sentry

### Configuration

| Variable | Default | Meaning |
|---|---|---|
| `SENTRY_DSN` | unset | When unset, Sentry is entirely disabled. |
| `SENTRY_ENVIRONMENT` | `development` | Environment tag on reported events. |
| `SENTRY_TRACES_SAMPLE_RATE` | `0.0` | Performance tracing is off by default. |

### Behaviour

`init_sentry()` returns immediately when `SENTRY_DSN` is unset or empty. This
makes the default posture "no data leaves the machine", and it makes the whole
feature verifiable locally: the disabled path is the one the test suite and
every developer machine exercise.

It is called immediately **after** `configure_logging()` in both entrypoints.
Ordering is load-bearing: Sentry's logging integration attaches to existing
handlers, so initializing it first would silently miss them.

`sentry-sdk` is added to base requirements. It is small and pure-Python, so it
does not undercut the image-slimming goal.

## Component 3 — `disk_guard.py`: LRU cache eviction

### Configuration

| Variable | Default | Meaning |
|---|---|---|
| `MAX_CACHE_MB` | `5120` | Combined ceiling across both caches. |

### Behaviour

`evict_caches()` runs at the top of `run_scan_pipeline`, before the clone. It
walks `CLONE_CACHE` and `incremental.CACHE_DIR`, keyed by the same
`md5(repo_url)` / `incremental._key(repo_url)` hash both already use, builds a
`(last_scan_time, bytes)` record per repository, and deletes
least-recently-scanned repositories until the combined total fits
`MAX_CACHE_MB`.

Inline rather than scheduled: no new service, no scheduler, and it behaves
identically in eager mode, in the worker container, and under pytest. The cost
is a directory-stat sweep on the scan path, which is negligible against a
`git clone`. The accepted downside is that a fully idle deployment reclaims
nothing until the next scan arrives — an idle deployment is also not filling
its disk.

### A clone and its prior are always evicted together

An orphaned prior is the dangerous direction. `run_scan_pipeline` gates the
incremental path on `prior and os.path.isdir(repo_dir/".git")`, so a surviving
prior whose clone was deleted falls through to a full clone and behaves
correctly. The reverse — a surviving clone whose prior was deleted — silently
loses history diffing and re-analyzes everything while reporting nothing
unusual. Evicting the pair atomically removes the need to reason about either
case.

### Last-scan time comes from the prior JSON's mtime

Not from the clone directory's mtime. A clone directory's mtime changes for
reasons unrelated to scanning — a `git fetch` that found nothing, an editor or
indexer touching the tree, an antivirus scan. The prior file is written exactly
once per completed scan, by `incremental.save_prior`, which makes its mtime an
accurate record of when the repository was last actually scanned.

## Component 4 — `disk_guard.py`: clone size watchdog

### Configuration

| Variable | Default | Meaning |
|---|---|---|
| `MAX_REPO_MB` | `1024` | Ceiling on a single cloned repository. |

### Behaviour

`clone_with_limit(url, dest, max_mb, timeout)` runs `git clone` under
`subprocess.Popen`. A daemon thread polls `dest`'s recursive size every two
seconds. On breach it kills the process, force-deletes the partial clone, and
raises `RepoTooLargeError` carrying the measured size. `run_scan_pipeline`'s
existing `except Exception` turns that into a scan error the UI already
renders, so no frontend change is required.

A post-clone verification catches the case where a repository lands over the
cap between two polls.

Git has no native size limit, which is why this is a watchdog rather than a
flag. Polling beats a pre-clone provider API query: an API check only covers
hosts that expose a size endpoint, adds a network round-trip to the scan path,
and is bypassed entirely by a self-hosted host. Polling beats a post-clone-only
check because by the time a post-clone check fires, the disk has already
absorbed the entire repository — that bounds the cache, not the peak.

### Shared helper: `force_rmtree()`

chmod-and-retry recursive delete. Git marks `objects/pack/*.idx` **read-only**,
so `shutil.rmtree` raises `PermissionError` (WinError 5) on Windows. This
already cost a full debugging round in `run_benchmark.py`, where
`ignore_errors=True` swallowed the error and left the directory in place, which
then made the next `git clone` fail with exit 128 on a non-empty destination.

Both eviction and the watchdog delete git directories, so both hit this. The
working implementation at `backend/benchmark/run_benchmark.py:223` is extracted
into `disk_guard.py` and `run_benchmark.py` is pointed at the shared copy —
rather than writing a third implementation of a bug that has already been
solved once.

## Component 5 — Image slimming

### Dependency split

`requirements.txt` loses `torch`, `transformers`, `sentence-transformers`,
`faiss-cpu`, and the `--extra-index-url` line for the CPU torch wheel. They
move to `requirements-ml.txt`, which carries the extra index URL. Both locks
are regenerated with pip-compile, matching how `requirements.lock` was produced
in Phase B — a `pip freeze` is the wrong artifact here and produced a
131-package dev-venv superset last time it was used.

The Dockerfile installs the base lock only.

### Two imports must go lazy

Without this, a base install fails at import, not at use:

- `llm_service.py:12` — the module-scope
  `from backend.app.services.retriever_service import CodeRetriever` moves
  inside the function that instantiates it at `llm_service.py:83`.
- `retriever_service.py:6,11` — `import faiss` and
  `from sentence_transformers import SentenceTransformer` move inside
  `get_embedding_model()` and `CodeRetriever.__init__`, with `ImportError`
  caught and folded into the **existing** graceful-degradation path.

`get_embedding_model()` already returns `None` when the model fails to load, and
`retrieve()` already falls back when the model or index is absent. Catching
`ImportError` into that same path means `test_retrieval.py`'s four tests —
which assert exactly that contract, that a list always comes back and
degradation is graceful — keep passing on a base install without being
rewritten. That is what makes this change safe.

`rag/ingest.py` keeps its top-level ML imports: it is a standalone script, never
imported by the application, and it is meaningless without the ML extra
installed.

## Testing

New test files, written test-first: `backend/tests/test_observability.py` and
`backend/tests/test_disk_guard.py`.

Real behavioural coverage, not smoke tests:

- **Eviction ordering and the cap** — fabricated cache directories with
  controlled mtimes and sizes; assert the least-recently-scanned repository goes
  first, that eviction stops as soon as the total fits, and that a clone and its
  prior are always removed as a pair.
- **The watchdog** — a fake clone command that writes a steadily growing file;
  assert the process is killed, `RepoTooLargeError` carries the measured size,
  and the partial directory is gone afterward. Also assert an under-cap clone
  completes untouched, so the guard cannot be passing by killing everything.
- **`force_rmtree`** — a directory containing a read-only file is deleted
  successfully.
- **Sentry** — asserted **off** with no DSN and initialized with one, SDK
  mocked, no network access in either case.
- **JSON logging** — the formatter emits parseable JSON carrying the `scan_id`
  set in the contextvar, `null` when no scan is in context; `configure_logging()`
  called twice attaches one handler, not two.

### Verification bar

No completion claim without fresh output from all of:

- `.\venv\Scripts\python.exe -m pytest` — 288/0 on the baseline. The global
  Python 3.13 has no fastapi and dies at collection; the venv interpreter is
  mandatory.
- `python backend/benchmark/run_benchmark.py --gate` — exit 0.
- `npx tsc -b` — never bare `tsc --noEmit`, which compiles zero files here
  because the root `tsconfig.json` is solution-style.
- `npm run build` — exit 0.

Docker is not installed on this machine. The slimmed image's build and boot are
**not verifiable locally** and will be reported as CI-verified or
user-verified, never claimed.

## Sequencing

One branch, `phase-e/ops-hardening`, five commits:

1. Extract `force_rmtree` into `disk_guard.py`; point `run_benchmark.py` at it.
2. LRU cache eviction, wired into `run_scan_pipeline`.
3. Clone size watchdog, replacing the raw `git clone` call.
4. `observability.py` — JSON logging, then Sentry.
5. Image slimming — last, because it is the commit that changes the locks and
   CI's install step, and it should land on top of a suite that is already
   green.

## Documentation

`.env.example` gains the seven new variables (`LOG_LEVEL`, `LOG_FORMAT`,
`SENTRY_DSN`, `SENTRY_ENVIRONMENT`, `SENTRY_TRACES_SAMPLE_RATE`,
`MAX_CACHE_MB`, `MAX_REPO_MB`) with the same commented-default style
it already uses. `DEPLOYMENT.md` gains a short operations section covering the
disk ceilings, how to turn Sentry on, and how to install the ML extra for a
deployment that actually wants retrieval.
