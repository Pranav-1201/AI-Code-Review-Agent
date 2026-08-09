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
