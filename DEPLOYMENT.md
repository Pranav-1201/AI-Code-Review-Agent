# Deployment — job queue & containers (Phase 6 / Chunk 5)

The API no longer runs scans in-process. `POST /scan` enqueues a Celery task onto
Redis; a **separate worker container** runs the scan and writes progress + the
final result to the SQLite scan store on a **shared volume**, which the API reads
back via `GET /scan/{scan_id}`.

```
  POST /scan ─▶ api ──enqueue──▶ Redis ──deliver──▶ worker ──run scan──┐
  GET /scan/{id} ◀── api ◀────── scan_states.db  (shared /data volume) ◀┘
```

Broker/backend are **env-driven** (`CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`).
With **no** `CELERY_BROKER_URL`, Celery runs **eager** (synchronous, in-process) —
that is the fallback for the test suite / CI / a bare local run. Real async
dispatch requires a broker, i.e. Docker. **Native Windows without Docker is not a
supported *async* path** (it falls back to eager, which blocks the request for the
whole scan).

## Run the stack

```bash
docker compose up --build
```

That builds one image (used by both `api` and `worker`) and starts `redis`, `api`,
and `worker`. First build is **multi-GB and slow** — `requirements.txt` pulls
torch/transformers/faiss (CPU wheels). Subsequent code-only rebuilds are fast
(deps are a cached layer).

## Verification checklist — please confirm on your Docker-capable machine

> Status: the **in-process (eager)** path and a **real out-of-process broker
> round-trip** are verified in-repo (see "Evidence" below). The **docker-compose
> boot is NOT verified by me** — Docker is not installed in the build environment.
> Treat the boxes below as unchecked until you run them.

1. **All three containers up**
   - `docker compose ps` → `redis`, `api`, `worker` all `Up` (redis `healthy`).
2. **Redis reachable**
   - `docker compose exec redis redis-cli ping` → `PONG`.
3. **Worker registered the task and is ready** (worker logs)
   - `docker compose logs worker` shows:
     - `celery@... ready.`
     - the task in the registered list: `. scan.run`
     - (if a scan was interrupted previously) `[worker] recovered N interrupted scan(s)...`
4. **API is serving**
   - `curl http://localhost:8000/` → `{"message":"AI Code Review Agent Running"}`.
5. **Enqueue a scan → worker picks it up out-of-process**
   - `curl -X POST http://localhost:8000/scan -H "Content-Type: application/json" -d '{"repo_path":"https://github.com/pallets/flask.git"}'`
     → returns `{"scan_id":"<uuid>"}` **immediately** (does not block for the scan).
   - `docker compose logs worker` then shows `Task scan.run[...] received` and,
     when finished, `Task scan.run[...] succeeded`.
6. **Status flows back through the shared volume**
   - `curl http://localhost:8000/scan/<uuid>` → status advances
     `starting → cloning → analyzing → finalizing → complete`
     (or `error` with a message). The API reads this from the same
     `scan_states.db` the worker wrote — proving the shared-volume round-trip.

## Environment variables

| Var | api | worker | Purpose |
|-----|-----|--------|---------|
| `CELERY_BROKER_URL` | ✅ | ✅ | Broker. Unset ⇒ eager mode. Compose: `redis://redis:6379/0`. |
| `CELERY_RESULT_BACKEND` | ✅ | ✅ | Optional; scan results persist in SQLite, not here. Compose: `redis://redis:6379/1`. |
| `SCAN_DB_PATH` | ✅ | ✅ | Scan store path. **Must be the same shared volume path in both** (`/data/scan_states.db`). |
| `API_KEY` | ✅ | — | Shared secret required in `X-API-Key`. **Unset ⇒ the API is open.** Worker serves no HTTP, so it has none. |
| `ALLOWED_ORIGINS` | ✅ | — | Comma-separated CORS origins. Default: localhost dev ports. Never `*`. |
| `ALLOWED_GIT_HOSTS` | ✅ | — | Comma-separated cloneable hosts. Setting it **replaces** the defaults (github/gitlab/bitbucket). |
| `RATE_LIMIT_PER_MINUTE` | ✅ | — | Per client, per route. Default 60. |

Full annotated list, including the frontend and LLM variables: **`.env.example`**.

### Security posture before exposing this to the internet

`POST /scan` runs `git clone` on a caller-supplied URL. That is expensive and
abusable, so before the API is reachable publicly:

1. **Set `API_KEY`** to a long random value. `GET /health` reports
   `"auth": "enabled"` — check it, because an unset key fails open, not closed.
2. **Set `ALLOWED_ORIGINS`** to the real frontend origin.
3. **Rebuild the frontend** with `VITE_API_BASE` and `VITE_API_KEY` set — Vite
   inlines these at build time, so changing them needs a rebuild, not a restart.
4. **Keep the reverse proxy in front.** `X-Forwarded-For` is trusted for the
   first hop when identifying clients for rate limiting; that header is
   spoofable if the app is exposed directly.

Repository URLs are validated before any clone: https-only, no embedded
credentials, host must be allowlisted, and literal private/loopback/link-local/
reserved IPs are rejected — which is what keeps `169.254.169.254` (cloud
metadata) and internal hosts out of reach even if the allowlist is widened.

### Dependency pinning

`requirements.lock` is a **pip-compile resolution** of `requirements.txt` — 76
pinned packages including transitives, with the `--extra-index-url` for the CPU
torch wheel baked in so the file is self-contained. CI and the Docker image both
install from it (`pip install -r requirements.lock`) so a transitive release
cannot silently change what ships between two builds of the same commit.
`requirements.txt` remains the loose human-edited declaration of intent.

It is deliberately **not** a `pip freeze`. Freezing this project's dev
virtualenv captured 131 packages including `chromadb`, `langchain`, `langgraph`,
`kubernetes` and `onnxruntime` — none declared, none imported — which would have
been baked into the production image. Regeneration command is in the lock header.

Two known gaps, both tracked for Phase E (image slimming): `pandas` and
`python-multipart` are declared in `requirements.txt` but imported nowhere, and
`torch` (~2 GB even as the CPU wheel) is pulled in for `llm_service.py` alone
despite the LLM path being gated off by default.

## Evidence already gathered (in-repo, no Docker)

- **Eager wiring** — `backend/tests/test_celery.py` (in the default suite): eager
  default without a broker; the task defers to `main.run_scan_pipeline`; worker
  owns zombie recovery; the API skips recovery in broker mode.
- **Real out-of-process dispatch** — `python backend/queue_roundtrip.py` spawns a
  real `celery worker` subprocess against a filesystem broker (no Redis), enqueues
  a task, and confirms it ran in a **different pid**. This is the Docker-free stand-in
  for step 5 above.
  (The script needs `pywin32` on Windows for the filesystem transport; it is a
  dev-only dep for the evidence run and is deliberately **not** in requirements.txt —
  production uses the Redis broker.)

## CI/CD (`.github/workflows/`)

**`ci.yml`** runs on every push to `main` or a `phase-*` branch and on every PR.
Two parallel jobs, running the same four commands that were previously only ever
run by hand on Windows:

| Job | Steps |
|-----|-------|
| `backend` | `pip install -r requirements.lock` → `pytest -q` → `run_benchmark.py --gate` |
| `frontend` | `npm ci` → `npx tsc --noEmit` → `npm run build` |

No environment variables are set, on purpose: every optional integration is off
by default, `API_KEY` unset exercises the open-API path, and `CELERY_BROKER_URL`
unset makes Celery run eagerly in-process — so **CI needs no Redis service**.

There is no `npm test` step yet. `package.json` wires vitest but the frontend has
zero test files, and vitest exits non-zero when it finds none — a red CI that
says nothing. The step lands with the tests (roadmap D/F5).

**`release.yml`** publishes the container image to GHCR. It is a separate
workflow gated on `workflow_run` of CI concluding `success`, because a published
image that never passed the tests is worse than no image — the tag implies it
did. It checks out `workflow_run.head_sha`, not whatever `main` points at when
it fires, so it cannot ship a different commit than the one CI validated.

### Rollback

Every image is tagged twice: the immutable **commit SHA** and `latest`. Rolling
back is re-deploying an explicit sha tag —

```
docker pull ghcr.io/<owner>/<repo>:<sha>
```

— rather than hoping a rebuild reproduces the previous state. Pair it with the
SQLite snapshot for data. The image name is lowercased in the workflow because
GHCR rejects uppercase paths and this repository's owner has capitals.

## Known caveats / deferred hardening

- **Single worker by design.** Zombie recovery reconciles *all* non-terminal scans
  at worker startup, which is only safe with one worker. Multiple workers/replicas
  need heartbeat-scoped recovery instead of reconcile-all. Don't set `deploy.replicas`
  on `worker` without that change.
- **SQLite on a shared volume** is fine on a single host (WAL is enabled), but is
  not a multi-host answer. Postgres is the path if the API and worker ever run on
  different hosts.
- **Rate limiting is in-process.** The counter lives in the API container's
  memory, which is exactly accurate for the single-API-container deployment this
  compose file describes. Scale the **api** service to N replicas and the
  effective limit silently becomes N × `RATE_LIMIT_PER_MINUTE`, because each
  replica counts only its own traffic. Moving to a shared Redis counter is the
  prerequisite for scaling the API — the broker is already there.
- **The API key is a single shared secret**, not per-user auth, and the frontend
  copy ships inside a public static bundle. It raises the cost of drive-by abuse
  of `/scan`; it does not identify or isolate callers. A login + short-lived
  token flow is the real answer if this ever serves more than its owner.
- **Clone-cache disk growth** (one full clone per repo_url, no eviction) is an
  open production-readiness item tracked separately — the clone cache is worker-local
  and ephemeral per container here, so it self-limits until the worker is given a
  persistent cache volume.

## Operations (Phase E)

### Disk ceilings

Two caches grow as repositories are scanned: a full git clone per distinct
repository URL, and a small JSON prior per repository used for incremental
re-analysis. Both are now bounded.

| Variable | Default | Effect |
|---|---|---|
| `MAX_CACHE_MB` | `5120` | Combined ceiling across both caches. When exceeded, least-recently-scanned repositories are evicted — clone and prior together — at the start of the next scan. |
| `MAX_REPO_MB` | `1024` | Ceiling on a single repository. A clone growing past it is killed mid-flight, the partial tree deleted, and the scan fails with a clear error. |

Eviction runs inline at the start of a scan, not on a timer. An idle
deployment therefore reclaims nothing until the next scan arrives — which is
also the moment it next needs the space. If a host is tight on disk, lower
`MAX_CACHE_MB` rather than adding a cron job.

Eviction is best-effort: if it fails (a directory locked longer than the
delete retry budget), it is logged and the scan proceeds. It is housekeeping,
not part of the scan's contract.

A clone and its prior are always evicted as a pair. An orphaned prior would be
the dangerous direction — the pipeline gates incremental analysis on both
existing, so a prior without its clone falls back to a full scan correctly,
while a clone without its prior would silently stop diffing history.

`MAX_REPO_MB` is the guard against a hostile or accidental giant repository.
The clone timeout is not a substitute: a fast link moves many gigabytes well
inside 300 seconds. A watchdog thread polls the clone directory and kills git
on breach, because git has no native size limit.

### Logs

Containers emit one JSON object per line — the Dockerfile sets
`LOG_FORMAT=json`. Every record carries `timestamp`, `level`, `logger`,
`message`, and `scan_id`, plus `exc_info` when an exception is attached.

`scan_id` is `null` outside a scan, so it is always present and filtering a
whole scan out of an aggregator is a single query. The root logger is
configured, so uvicorn and celery records are included.

| Variable | Default | Effect |
|---|---|---|
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`. |
| `LOG_FORMAT` | `text` | `text` or `json`. The Dockerfile overrides this to `json`. |

Set `LOG_FORMAT=text` when tailing a container by hand and you want it
readable.

### Error reporting

Sentry is off unless `SENTRY_DSN` is set — with no DSN configured, nothing is
sent anywhere. To turn it on, set the DSN and optionally `SENTRY_ENVIRONMENT`
(default `development`), then restart the API and the worker.

`SENTRY_TRACES_SAMPLE_RATE` defaults to `0.0`; raise it only if you want
performance tracing and accept the cost.

### Optional ML stack

The production image does **not** install `torch`, `transformers`,
`sentence-transformers`, or `faiss-cpu`. No shipped configuration could reach
that code: no FAISS index is built into the image, so retrieval takes its
fallback path, and `ENABLE_CODEBERT` defaults to `false`. Removing them took
the base lock from 282 pinned packages to 163 and dropped the multi-gigabyte
CPU-torch wheel.

A deployment that genuinely wants CodeBERT scoring or FAISS retrieval needs
both locks, and an index built into the image:

```
pip install -r requirements.lock -r requirements-ml.lock
```

Without the extra installed, the retrieval and CodeBERT paths degrade quietly
and log at warning level. They do not fail the scan.
