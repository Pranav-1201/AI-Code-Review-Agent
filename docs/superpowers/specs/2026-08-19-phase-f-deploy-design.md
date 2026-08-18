# Phase F — Deploy: design

**Date:** 2026-08-19
**Branch:** `phase-f/deploy`
**Baseline:** `main` = `69b941e` (Phase E shipped, CI green, pytest 324/0)
**Status:** implemented on `phase-f/deploy`; corrections from implementation folded back in

---

## 1. Goal and non-goals

### Goal

Make this repository deployable to a single VPS by someone following a written
checklist, with a rollback that does not depend on rebuilding, and a backup that
survives the container being destroyed.

Phase A–E made the application production-*grade*. Nothing in the repository has
ever been production-*deployed*: `docker compose up` has never been executed by
this project (Docker is not installed on the development machine), there is no
TLS story, there is no frontend hosting story, and the SQLite scan store has no
backup at all.

### Non-goals

Explicitly out of scope. Each is deferred with a reason, not forgotten:

- **Real authentication.** The shared `API_KEY` stays a shared key. Login +
  short-lived tokens is roadmap item G. Section 4.1 restates why the key in the
  frontend bundle is acceptable-but-limited rather than a defect to fix here.
- **Postgres.** SQLite on a shared volume is correct for a single host and is
  what the existing worker/zombie-recovery design assumes.
- **Multi-replica API or worker.** Both have documented blockers (in-process
  rate limiting; reconcile-all zombie recovery). Scaling either is a design
  change, not a deployment change.
- **The deferred dependency majors** (`vite` → 8.x, `react-router-dom` → 7.x).
  Three-major and one-major jumps with no in-range fix; a dependency task, not a
  deployment task.
- **Any cloud provider automation** (Terraform, Ansible, provider CLIs). The
  runbook is manual by design: this is one host, provisioned once.

---

## 2. The constraint that shapes everything: no Docker here

`docker` is not installed on the development machine and is not installable
within this session (`where.exe docker` → not found; verified 2026-08-19).

This is the same constraint Phase E hit when it slimmed the image, and it is
handled the same way: **author everything, verify what is verifiable, and mark
the rest explicitly user-verified rather than quietly implying it was tested.**

What CAN be verified locally:

| Artifact | Verification | Tool |
|---|---|---|
| `docker-compose.prod.yml` | parses as YAML, expected services/keys present | `python -c "import yaml..."` |
| `frontend/Dockerfile` | *nothing locally* — built and run by the CI `deploy-stack` job | — |
| `Caddyfile` | *nothing locally* — exercised by the CI `deploy-stack` job | — |
| Frontend still builds | exit 0 | `npm run build` |
| Types still check | exit 0 | `npx tsc -b` |
| Backend unaffected | 324/0 | `.\venv\Scripts\python.exe -m pytest` |

**Corrected during implementation.** The original draft of this section said the
image build and the stack boot could not be verified at all. That was true of
*this machine* and false of *CI*: the GitHub runner has Docker, and `release.yml`
was already building images on it. A `deploy-stack` job now builds both images,
renders the merged compose configuration, boots the stack, and drives it through
Caddy — asserting the `/api` prefix is stripped, that a deep link returns the SPA
shell, that port 8000 is not published, and that a backup snapshot is written.

So the following are **gated in CI**, not assumed: images build, stack boots,
Caddy's configuration is valid, the proxy reaches the API.

What genuinely remains unverified until someone deploys: **TLS issuance, real
DNS, and behaviour under load.** The CI job runs on `:80` with no hostname, so
it never exercises ACME. The DEPLOYMENT.md checklist covers exactly that
remainder.

---

## 3. Topology

Decided: **all-on-VPS, single origin.** Rejected: frontend on Vercel with the
API on the VPS (the roadmap's original line).

```
                     ┌──────────────────────────────────────────┐
   internet  ──443──▶│ web  (caddy:2-alpine + built dist)       │
                     │   /*      → file_server  (React SPA)     │
                     │   /api/*  → reverse_proxy api:8000       │
                     └───────┬──────────────────────────────────┘
                             │ (compose network, not published)
                     ┌───────▼────────┐      ┌──────────────────┐
                     │ api            │      │ worker           │
                     │ uvicorn :8000  │      │ celery, conc=2   │
                     └───┬────────┬───┘      └───┬──────────┬───┘
                         │        │              │          │
                    ┌────▼───┐  ┌─▼──────────────▼──┐  ┌────▼─────┐
                    │ redis  │  │ scan-data volume  │  │ backup   │
                    │ :6379  │  │ scan_states.db    │  │ sqlite   │
                    └────────┘  └───────────────────┘  └──────────┘
```

### Why single origin

The alternative (Vercel frontend, VPS API) keeps CORS as a live, mutable
configuration surface that must be kept in sync with a hostname the backend
never sees. Serving both from one origin removes an entire class of deployment
failure: `ALLOWED_ORIGINS` can remain unset in production, because a same-origin
request has no CORS preflight to fail. It also means one thing to operate, one
TLS certificate, and no second vendor account.

The cost is that the frontend is no longer on a CDN. For a self-hosted analysis
tool rather than a consumer site, that is not a real cost.

### Port exposure changes

In `docker-compose.yml` (dev) the `api` service publishes `8000:8000`. In the
production overlay it **must not**: publishing it puts an
unauthenticated-by-default API on the public internet beside the proxy,
bypassing Caddy, its TLS, and its `X-Forwarded-For` normalization (§4.2c). The
overlay therefore removes the published port, and the API becomes reachable only
on the compose network.

---

## 4. Component design

### 4.1 `frontend/Dockerfile` — two stages

Stage 1, `node:20-alpine` (matches `ci.yml`, the only version this frontend
has evidence of building under): `npm ci` →
`npm run build` → `/app/dist`.

Stage 2, `caddy:2-alpine`: copy `dist` to `/srv`, copy `Caddyfile` to
`/etc/caddy/Caddyfile`.

**Build args, and the trap in them:**

```
ARG VITE_API_BASE=/api
ARG VITE_API_KEY=
```

Vite inlines `import.meta.env.VITE_*` at build time, so both values are baked
into the shipped JavaScript. `VITE_API_BASE=/api` is the whole point of the
single-origin design: the bundle makes relative requests and therefore works
under any hostname without a rebuild.

`VITE_API_KEY` is different and needs a comment in the file itself, because an
argument named `*_KEY` invites the assumption that it is a secret. It is not —
anything inlined into a static bundle is readable by anyone who loads the page.
`frontend/src/lib/api.ts:8-14` already documents this. Repeating it at the build
boundary is deliberate: that is where someone will be tempted to pass a real
secret.

**Build context is the repository root**, matching `backend/Dockerfile`, because
the `Caddyfile` lives at the root beside `docker-compose.yml`. That also means no
`frontend/.dockerignore` is needed: the root `.dockerignore` already excludes
`frontend/node_modules/` and `frontend/dist/`, which would otherwise be slow to
send and could shadow the `npm ci` result.

### 4.2 `Caddyfile`

```
{$SITE_ADDRESS::80} {
	handle_path /api/* {
		reverse_proxy api:8000 {
			header_up X-Forwarded-For {remote_host}
		}
	}
	handle {
		root * /srv
		try_files {path} /index.html
		file_server
	}
}
```

Four decisions, each load-bearing:

**(a) `{$SITE_ADDRESS::80}`.** Caddy substitutes the env var, defaulting to
`:80`. Unset, the stack boots on any machine over plain HTTP — which is what
makes a first `docker compose up` on a laptop possible at all. Set to a real
hostname, Caddy performs ACME issuance automatically with no other change. One
variable is the entire TLS story.

**(b) `handle_path`, not `handle`.** `handle_path` strips the matched prefix
before proxying, so `/api/scan/{id}/stream` arrives at the backend as
`/scan/{id}/stream`. This matters beyond routing: `api_guard.is_stream_path`
matches on the request path to permit the `?api_key=` query-string carve-out
that `EventSource` requires (it cannot set headers). A non-stripping proxy would
present `/api/scan/{id}/stream`, `is_stream_path` would not match, and SSE would
fail with a 401 that looks like an auth bug rather than a routing bug.

**(c) `header_up X-Forwarded-For {remote_host}` — a security fix, not
boilerplate.** `backend/app/api_guard.py:250-252` reads:

```python
forwarded = request.headers.get("X-Forwarded-For", "")
if forwarded:
    return forwarded.split(",")[0].strip()
```

It trusts the *first* entry. Caddy's `reverse_proxy` by default **appends** the
peer address to any inbound `X-Forwarded-For`, so a request arriving with
`X-Forwarded-For: 1.2.3.4` is forwarded as `1.2.3.4, <real-ip>` and the rate
limiter buckets on the client-supplied value. Rotating that header defeats
`RATE_LIMIT_PER_MINUTE` completely — on `/scan`, the route that performs
`git clone`, which is the most abusable operation the service exposes.

Overwriting instead of appending makes the header equal to the actual peer.

This is latent rather than live today only because nothing has ever been
deployed behind a proxy. The trusting `split(",")[0]` is correct *given* a
trustworthy proxy; Phase F is what introduces the proxy, so Phase F is what owes
the guarantee.

**(d) `try_files {path} /index.html`.** React Router is a client-side router, so
a deep link such as `/history/abc` has no file on disk and must be served the SPA
shell. Without this, every refresh on a non-root route 404s.

### 4.3 `docker-compose.prod.yml` — overlay, not replacement

Used as `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d`.
An overlay rather than a standalone file so the dev topology remains the single
description of services, wiring, and volumes, and the overlay expresses only what
production changes. Two full files would drift.

What the overlay changes:

- `api`, `worker`: replace `build:` with
  `image: ghcr.io/<owner>/<repo>:${IMAGE_TAG:-latest}`. This is what makes
  `release.yml`'s sha tagging an actual rollback mechanism (§4.5).
- `api`: remove the published `8000:8000` (§3), add `restart: unless-stopped`,
  add a healthcheck against `/health`.
- `redis`, `worker`: `restart: unless-stopped`.
- New `web` service: publishes `80:80` and `443:443`, named volumes for
  `caddy_data` (certificates) and `caddy_config`, `depends_on: api`.
- New `backup` service (§4.4).

`caddy_data` must be a named volume. Without persistence Caddy re-issues
certificates on every restart and will hit Let's Encrypt rate limits.

### 4.4 Backup: `scripts/backup-sqlite.sh` + `scripts/restore-sqlite.sh`

A small `alpine` service with `sqlite` installed, looping:

```sh
sqlite3 "$DB" ".backup '$DEST/scan-$(date -u +%Y%m%dT%H%M%SZ).db'"
```

**`.backup`, never `cp`.** The store runs in WAL mode. Copying the `.db` file
while a writer is active captures a torn state — committed data may live in
`-wal` and not yet in the main file. `.backup` uses SQLite's online backup API
and produces a consistent single-file snapshot regardless of concurrent writes.

Rotation keeps the newest `BACKUP_KEEP` (default 7) and deletes older ones. The
interval is `BACKUP_INTERVAL_SECONDS` (default 86400). Both are env vars so the
policy is visible in `.env` rather than buried in a script.

`restore-sqlite.sh` is a separate script because restoring is not the inverse of
backing up: it must stop the writers first, then replace the file, then remove
the stale `-wal` and `-shm` sidecars. Leaving those beside a restored main file
is how a "successful" restore silently resurrects pre-restore data.

Backup failures are logged and do not kill the loop. A backup service that exits
on one bad night stops protecting every subsequent night, which is worse than a
noisy log.

### 4.5 `release.yml` — publish the web image too

Currently one image is built and pushed. With a `web` service, a sha-tagged
rollback covering only the API is not a rollback: the frontend bundle and the API
it calls are versioned together and can disagree about request shapes.

A second build/push step tags `.../<repo>-web:<sha>` and `:latest` from
`frontend/Dockerfile`, with the same `workflow_run` gating and the same
lowercasing (GHCR rejects uppercase paths; this owner has capitals).

`VITE_API_BASE=/api` is passed as a build arg at publish time. `VITE_API_KEY` is
deliberately **not** passed in CI — a published image is a public artifact, and
baking a key into it would publish the key. A deployment that wants the key set
builds the web image on the host instead, and the runbook says so explicitly.

---

## 5. Documentation changes

### 5.1 `DEPLOYMENT.md` — new VPS section

The existing file documents the dev compose stack. Phase F adds a first-deploy
runbook: provision, DNS, `.env`, first boot, verification checklist, upgrade,
rollback, restore, and a pointer to the operational surface Phase E already
shipped (disk ceilings, JSON logs, Sentry).

Every step this session could not execute is marked operator-verified. The
document must not read as though the stack has been booted.

### 5.2 `DEPLOYMENT.md` — a stale caveat to correct

The "Known caveats / deferred hardening" list currently states that clone-cache
disk growth has "no eviction" and is "an open production-readiness item".

Phase E shipped LRU eviction across both caches and a clone-size watchdog, and
the *same file* documents them under "Operations (Phase E) → Disk ceilings". The
file contradicts itself. The caveat is corrected to describe what is actually
still true: the ceilings are per-host and configured by env var, and giving the
worker a persistent cache volume changes the arithmetic.

### 5.3 `.env.example` — production block

New documented variables: `SITE_ADDRESS`, `IMAGE_TAG`, `BACKUP_INTERVAL_SECONDS`,
`BACKUP_KEEP`, `BACKUP_DIR`, plus a short block stating that for an
internet-facing deployment `API_KEY` is no longer optional. The file's current
claim that "every variable below is OPTIONAL" holds for local dev and stops
holding the moment the host is public.

---

## 6. Testing strategy

Phase F is configuration and documentation. It adds no Python and no TypeScript,
so it adds no unit tests — a test asserting the *contents* of a YAML file tests
the file against itself.

**A pytest-based compose check was planned and rejected.** It would have needed
`import yaml`, and `pyyaml` is not a declared dependency: it appears only in
`requirements-ml.lock`, which neither the production image nor the CI backend job
installs. It imports on the development machine solely because the dev venv still
carries the ML stack. Such a test would have passed locally and died at collection
in CI — the same failure Phase E hit with `httpx`, from the same cause. It would
also have been the weaker check: `docker compose config` validates the *merged*
base-plus-overlay result, which is the thing that actually has to work.

What is tested, and where:

| Claim | Gate |
|---|---|
| Both images build | CI `deploy-stack` |
| Base and overlay merge into a valid configuration | CI `deploy-stack` (`docker compose config`) |
| The stack boots and the API reaches `healthy` | CI `deploy-stack` |
| Caddy strips the `/api` prefix | CI `deploy-stack` (`GET /api/health`) |
| Deep links serve the SPA shell | CI `deploy-stack` (`GET /history/deep-link`) |
| Port 8000 is not published | CI `deploy-stack` (negative check) |
| A backup snapshot is actually written | CI `deploy-stack` |
| The frontend still builds and typechecks | local + CI `frontend` |
| The backend is untouched | local + CI `backend` (324 passed) |

Explicitly NOT tested, because nothing available can test it: **TLS issuance,
real DNS, and behaviour under load.** The CI job runs on `:80` with no hostname,
so ACME is never exercised. That remainder is the content of the operator
checklist in §5.1 — and it is a much shorter list than this document originally
assumed.

---

## 7. Risks

| Risk | Mitigation |
|---|---|
| Caddyfile has a syntax error nobody can catch here | First runbook step is `docker compose ... config` plus `caddy validate` inside the image, before any `up` |
| Operator deploys with `API_KEY` unset | `/health` reports `"auth": "disabled"`; the checklist makes confirming it a required step |
| Operator publishes `8000` "to test it" | The overlay's removal of the port carries a comment with the reason |
| ACME fails behind a firewall | Runbook states :80 and :443 must both be open — :80 is required for the HTTP-01 challenge even when only :443 serves traffic |
| Backups accumulate until the disk fills | `BACKUP_KEEP` rotation, default 7. The Phase E disk ceilings do not cover the backup directory |
| Restore leaves stale `-wal`/`-shm` | The restore script removes them; doing it by hand is the documented failure |

---

## 8. Files

**New:** `frontend/Dockerfile`, `frontend/.dockerignore`, `Caddyfile`,
`docker-compose.prod.yml`, `scripts/backup-sqlite.sh`, `scripts/restore-sqlite.sh`

**Edited:** `.env.example`, `DEPLOYMENT.md`, `.github/workflows/release.yml`

**Unchanged:** all application code. If this phase modifies `backend/` or
`frontend/src/`, something has been misunderstood — with one possible exception.

**Possible exception:** §4.2(c) argues the `X-Forwarded-For` trust in
`api_guard.client_identity` is safe only behind a normalizing proxy. The
Caddyfile provides that. If implementation shows the guarantee cannot be made
config-only, hardening `client_identity` itself comes into scope, and that would
carry a unit test.
