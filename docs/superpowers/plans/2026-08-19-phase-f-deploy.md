# Phase F — Deploy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the stack deployable to a single VPS behind Caddy with automatic TLS, a sha-tagged rollback, and a WAL-safe SQLite backup — and prove in CI that the images build and the stack actually boots.

**Architecture:** One new `web` tier (Caddy serving the built React bundle at `/` and reverse-proxying `/api/*` to the API container) turns the deployment into a single origin, which removes CORS as a live configuration surface. A production compose *overlay* changes only what production changes: images pulled by tag instead of built, no published API port, restart policies, plus `web` and `backup` services. A new CI job builds both images and boots the merged stack, converting the project's longest-standing unverified claim into an automated gate.

**Tech Stack:** Docker Compose, Caddy 2 (alpine), Node 20 (alpine) build stage, SQLite online-backup API, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-08-19-phase-f-deploy-design.md` (committed `39e4d7e`)

## Global Constraints

- **No application code changes.** No file under `backend/` or `frontend/src/` is modified by this plan. If a task appears to need one, stop and escalate.
- **Docker is not available on the development machine.** No step may claim an image builds or a stack boots based on local execution. The only evidence for those claims is the CI job built in Task 4.
- **`pyyaml` is NOT a declared dependency.** It appears only in `requirements-ml.lock`, which the base image and the CI backend job do not install. It is importable in the dev venv only because the ML stack is still installed there. **No test added by this plan may `import yaml`.**
- **Node version is `20`.** `.github/workflows/ci.yml:88` builds this frontend on Node 20 and that is the only version with evidence behind it. The local machine has v22.14.0; do not use it as the image base.
- **Image repository is `ghcr.io/pranav-1201/ai-code-review-agent`** — lowercased from `Pranav-1201/AI-Code-Review-Agent`, because GHCR rejects uppercase paths.
- **Build context for every Dockerfile is the repository root.** `backend/Dockerfile` already works this way. The root `.dockerignore` is therefore the only ignore file needed.
- **Commit messages carry no AI attribution** — no `Co-Authored-By` naming an assistant, no "Generated with" line. See `CLAUDE.md`.
- Shell scripts are `sh`-compatible (they run in `alpine`), not bash-only.

---

### Task 1: Web tier — Caddyfile and frontend image

**Files:**
- Create: `Caddyfile`
- Create: `frontend/Dockerfile`
- Test: none locally — verified by the CI job in Task 4

**Interfaces:**
- Consumes: nothing.
- Produces: an image that serves `/srv` (the built SPA) and proxies `/api/*` to host `api` port `8000`; honours env var `SITE_ADDRESS`; accepts build args `VITE_API_BASE` and `VITE_API_KEY`. Task 3 references the image, Task 4 builds it, Task 5 publishes it.

- [ ] **Step 1: Create `Caddyfile` at the repository root**

```
# ==========================================================
# Phase F — the public edge. Serves the built React bundle and proxies the
# API, so the whole application is ONE origin.
#
# Single origin is the point: a same-origin request has no CORS preflight to
# fail, so ALLOWED_ORIGINS can stay unset in production instead of being a
# second place a hostname has to be kept in sync.
# ==========================================================

# SITE_ADDRESS unset -> ":80", i.e. plain HTTP on any machine, which is what
# makes a first `docker compose up` on a laptop work at all. Set it to a real
# hostname and Caddy performs ACME issuance automatically, with no other
# change anywhere. This one variable is the entire TLS story.
{$SITE_ADDRESS::80} {

	# handle_path (not handle) STRIPS the /api prefix before proxying, so
	# /api/scan/{id}/stream reaches the backend as /scan/{id}/stream.
	#
	# That is load-bearing beyond routing: api_guard.is_stream_path matches on
	# the request path to allow the ?api_key= carve-out that EventSource needs
	# (it cannot set headers). Without stripping, the backend would see
	# /api/scan/{id}/stream, is_stream_path would not match, and SSE would fail
	# with a 401 that looks like an auth bug rather than a routing bug.
	handle_path /api/* {
		reverse_proxy api:8000 {
			# OVERWRITE, never append. api_guard.client_identity trusts the
			# FIRST entry of X-Forwarded-For, and reverse_proxy's default is to
			# append the peer to whatever the client sent. A request arriving
			# with a forged "X-Forwarded-For: 1.2.3.4" would be forwarded as
			# "1.2.3.4, <real ip>", letting the caller choose its own rate-limit
			# bucket — and rotating that value defeats RATE_LIMIT_PER_MINUTE
			# entirely on /scan, the route that runs `git clone`.
			#
			# {remote_host} is the actual peer, so the header cannot be forged.
			header_up X-Forwarded-For {remote_host}
		}
	}

	handle {
		root * /srv
		# React Router is client-side: /history/abc has no file on disk, so a
		# refresh on any non-root route 404s without this line.
		try_files {path} /index.html
		file_server
	}

	encode gzip
}
```

- [ ] **Step 2: Create `frontend/Dockerfile`**

Note the build context is the repository ROOT (matching `backend/Dockerfile`), which is why every `COPY` source is prefixed with `frontend/` and why the root `Caddyfile` is reachable.

```dockerfile
# ==========================================================
# Phase F — the web tier: build the React bundle, then serve it from Caddy
# alongside a reverse proxy to the API. One image, two stages.
#
# Build context is the REPO ROOT (same as backend/Dockerfile), because the
# Caddyfile lives at the root next to docker-compose.yml. The root
# .dockerignore already excludes frontend/node_modules and frontend/dist.
# ==========================================================

# Node 20 to match .github/workflows/ci.yml, which is the only version this
# frontend has evidence of building under. The dev machine has 22; that is not
# a reason to build the shipped artifact with it.
FROM node:20-alpine AS build

WORKDIR /app

# Dependencies first so the install layer survives code-only rebuilds.
# `npm ci` (not install) installs exactly the lockfile and fails if
# package.json and package-lock.json have drifted apart.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./

# Vite INLINES import.meta.env.VITE_* at build time, so both of these are
# baked into the shipped JavaScript and travel with the image.
#
# VITE_API_BASE=/api is the whole point of the single-origin design: the
# bundle issues relative requests, so the same image works under any hostname
# with no rebuild.
ARG VITE_API_BASE=/api
ENV VITE_API_BASE=$VITE_API_BASE

# VITE_API_KEY is NOT a secret, despite the name, and this is the boundary
# where someone will be tempted to treat it as one. Anything inlined into a
# static bundle is readable by anyone who loads the page. It raises the cost of
# drive-by abuse of /scan; it does not identify or isolate callers. See
# frontend/src/lib/api.ts:8-14. Real per-user auth is roadmap item G.
#
# Deliberately left empty by default, and deliberately NOT passed by
# release.yml: a published image is a public artifact, so baking a key into one
# publishes the key.
ARG VITE_API_KEY=
ENV VITE_API_KEY=$VITE_API_KEY

RUN npm run build


FROM caddy:2-alpine

COPY --from=build /app/dist /srv
COPY Caddyfile /etc/caddy/Caddyfile

EXPOSE 80 443
```

- [ ] **Step 3: Confirm the frontend still builds and typechecks unchanged**

This does not test the image — nothing local can. It confirms the task did not disturb the frontend, which is the only claim available here.

Run:
```bash
cd frontend && npx tsc -b && npm run build
```
Expected: both exit 0. The build prints the same chunk list as before, with the entry chunk near 387 kB.

- [ ] **Step 4: Confirm no application code was touched**

Run:
```bash
git status --porcelain
```
Expected: exactly two new untracked paths, `Caddyfile` and `frontend/Dockerfile`. Nothing under `frontend/src/` or `backend/`. If `frontend/dist/` appears, it is gitignored — confirm with `git check-ignore -v frontend/dist`.

- [ ] **Step 5: Commit**

```bash
git add Caddyfile frontend/Dockerfile
git commit -F - <<'EOF'
Serve the app and the API from one origin behind Caddy

The frontend has had no production host and the API no TLS. This adds the
web tier: a two-stage image that builds the React bundle and serves it from
Caddy, which also proxies /api to the API container.

Same origin means a request has no CORS preflight to fail, so ALLOWED_ORIGINS
stops being a second place a hostname must be kept in sync.

The X-Forwarded-For override is not boilerplate. api_guard.client_identity
trusts the first entry of that header, and reverse_proxy appends to whatever
the client sent, so without the override a caller could pick its own
rate-limit bucket and rotate it to bypass the limit on the route that clones
repositories.
EOF
```

---

### Task 2: WAL-safe SQLite backup and restore

**Files:**
- Create: `scripts/backup-sqlite.sh`
- Create: `scripts/restore-sqlite.sh`
- Test: none locally — `sqlite3` is not required to be present on the dev machine; verified by review and by the operator checklist

**Interfaces:**
- Consumes: nothing.
- Produces: `scripts/backup-sqlite.sh`, an infinite loop suitable as a container `command`, configured by env vars `DB_PATH` (default `/data/scan_states.db`), `BACKUP_DIR` (default `/backups`), `BACKUP_INTERVAL_SECONDS` (default `86400`), `BACKUP_KEEP` (default `7`). Task 3 mounts and runs it; Task 6 documents the same four variable names.

- [ ] **Step 1: Create `scripts/backup-sqlite.sh`**

```sh
#!/bin/sh
# ==========================================================
# Phase F — periodic snapshot of the scan store.
#
# Uses sqlite3 ".backup", NEVER `cp`. The store runs in WAL mode, so copying
# the .db file while a writer is active captures a torn state: committed data
# may still live in the -wal sidecar and not yet in the main file. ".backup"
# uses SQLite's online backup API and produces a consistent single-file
# snapshot regardless of concurrent writes.
# ==========================================================
set -eu

DB_PATH="${DB_PATH:-/data/scan_states.db}"
BACKUP_DIR="${BACKUP_DIR:-/backups}"
BACKUP_INTERVAL_SECONDS="${BACKUP_INTERVAL_SECONDS:-86400}"
BACKUP_KEEP="${BACKUP_KEEP:-7}"

log() {
	# Matches the backend's operational convention: one line, timestamped,
	# greppable. Not JSON — this runs in a stock alpine container with no
	# Python, and inventing a second JSON emitter here would be worse than a
	# plain line.
	echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) backup: $*"
}

mkdir -p "$BACKUP_DIR"

log "started; db=$DB_PATH dir=$BACKUP_DIR interval=${BACKUP_INTERVAL_SECONDS}s keep=$BACKUP_KEEP"

while true; do
	if [ ! -f "$DB_PATH" ]; then
		# Not an error: the store is created lazily on the first scan, so an
		# untouched deployment legitimately has no database yet.
		log "no database at $DB_PATH yet; skipping this cycle"
	else
		dest="$BACKUP_DIR/scan-$(date -u +%Y%m%dT%H%M%SZ).db"

		# A failed backup must NOT kill the loop. A service that exits on one
		# bad night stops protecting every subsequent night, which is strictly
		# worse than a noisy log.
		if sqlite3 "$DB_PATH" ".backup '$dest'"; then
			log "wrote $dest ($(wc -c <"$dest") bytes)"

			# Rotation: keep the newest $BACKUP_KEEP, delete the rest. Sorted
			# by name, which is chronological because the timestamp is a
			# zero-padded UTC basic-format string.
			ls -1 "$BACKUP_DIR"/scan-*.db 2>/dev/null \
				| sort -r \
				| tail -n +"$((BACKUP_KEEP + 1))" \
				| while read -r old; do
					rm -f "$old" && log "rotated out $old"
				done
		else
			log "ERROR backup failed; leaving previous snapshots in place"
			rm -f "$dest"
		fi
	fi

	sleep "$BACKUP_INTERVAL_SECONDS"
done
```

- [ ] **Step 2: Create `scripts/restore-sqlite.sh`**

Restoring is not the inverse of backing up, which is why this is a separate script rather than a flag.

```sh
#!/bin/sh
# ==========================================================
# Phase F — restore the scan store from a snapshot.
#
# Run this from the repository root ON THE HOST, with the stack stopped:
#
#   docker compose -f docker-compose.yml -f docker-compose.prod.yml down
#   ./scripts/restore-sqlite.sh /var/lib/acra-backups/scan-20260819T000000Z.db
#   docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
#
# This is NOT the inverse of backup-sqlite.sh. Two things make it different:
#   1. Writers must be stopped first. Replacing the file under a live worker
#      gives you a corrupt database and a confusing incident.
#   2. The -wal and -shm sidecars MUST be removed. Leaving them beside a
#      restored main file is how a "successful" restore silently resurrects
#      pre-restore data: SQLite replays the stale WAL on next open.
# ==========================================================
set -eu

SNAPSHOT="${1:-}"
DB_PATH="${DB_PATH:-/var/lib/docker/volumes/etproject_scan-data/_data/scan_states.db}"

if [ -z "$SNAPSHOT" ]; then
	echo "usage: $0 <snapshot.db>" >&2
	echo "" >&2
	echo "DB_PATH may be overridden; it currently points at:" >&2
	echo "  $DB_PATH" >&2
	echo "" >&2
	echo "Find the real path with:" >&2
	echo "  docker volume inspect etproject_scan-data" >&2
	exit 2
fi

if [ ! -f "$SNAPSHOT" ]; then
	echo "no such snapshot: $SNAPSHOT" >&2
	exit 1
fi

# Refuse to restore a file SQLite cannot read, rather than replacing a good
# database with a broken one and discovering it at the next scan.
if ! sqlite3 "$SNAPSHOT" "pragma integrity_check;" | head -1 | grep -qx "ok"; then
	echo "snapshot failed integrity_check; refusing to restore: $SNAPSHOT" >&2
	exit 1
fi

echo "restoring $SNAPSHOT -> $DB_PATH"

if [ -f "$DB_PATH" ]; then
	aside="$DB_PATH.pre-restore-$(date -u +%Y%m%dT%H%M%SZ)"
	mv "$DB_PATH" "$aside"
	echo "previous database moved aside: $aside"
fi

cp "$SNAPSHOT" "$DB_PATH"

# The sidecars belong to the database that was just moved aside, not to the
# one just restored. See the header comment.
rm -f "$DB_PATH-wal" "$DB_PATH-shm"

echo "done. Start the stack and confirm GET /api/health responds."
```

- [ ] **Step 3: Mark both scripts executable in git's index**

Git on Windows will not set the mode from the filesystem, and a script checked out without the executable bit fails inside the container.

Run:
```bash
git add scripts/backup-sqlite.sh scripts/restore-sqlite.sh
git update-index --chmod=+x scripts/backup-sqlite.sh scripts/restore-sqlite.sh
git ls-files -s scripts/
```
Expected: both lines begin with mode `100755`, not `100644`. If either shows `100644`, re-run the `--chmod=+x` for that path.

- [ ] **Step 4: Check the scripts for shell syntax errors**

`sh -n` parses without executing, so it works even though `sqlite3` is absent here.

Run:
```bash
sh -n scripts/backup-sqlite.sh && sh -n scripts/restore-sqlite.sh && echo "syntax OK"
```
Expected: `syntax OK`.

- [ ] **Step 5: Commit**

```bash
git commit -F - <<'EOF'
Snapshot the scan store on a timer, and make restores survivable

The scan store has had no backup of any kind. These two scripts add one and
document the restore path.

Backup uses sqlite3 ".backup" rather than copying the file: the store runs in
WAL mode, so a plain copy taken while a scan is writing can capture a torn
state with committed data still in the sidecar.

Restore is a separate script because it is not the inverse operation. It has
to stop writers first and delete the -wal and -shm sidecars, which otherwise
get replayed over the restored file and quietly bring the old data back.

A failed backup logs and continues rather than exiting, so one bad night
cannot silently end all future backups.
EOF
```

---

### Task 3: Production compose overlay

**Files:**
- Create: `docker-compose.prod.yml`
- Test: none locally — verified by the CI job in Task 4

**Interfaces:**
- Consumes: `frontend/Dockerfile` and `Caddyfile` (Task 1); `scripts/backup-sqlite.sh` (Task 2).
- Produces: services `web` and `backup`; the env vars `IMAGE_REPO`, `WEB_IMAGE_REPO`, `IMAGE_TAG`, `SITE_ADDRESS`, `BACKUP_HOST_DIR`, `BACKUP_INTERVAL_SECONDS`, `BACKUP_KEEP`. Task 4 sets `IMAGE_REPO`/`WEB_IMAGE_REPO`/`IMAGE_TAG`; Task 6 documents all of them. Note `BACKUP_HOST_DIR` (host side, set by the operator) is distinct from the container-internal `BACKUP_DIR`, which is pinned to `/backups` in the service definition and is not an operator knob.

- [ ] **Step 1: Create `docker-compose.prod.yml`**

```yaml
# ==========================================================
# Phase F — production overlay. Used WITH the base file, never instead of it:
#
#   docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
#
# An overlay rather than a second full stack description, so the base file
# stays the single definition of services, wiring, and volumes and this file
# expresses only what production changes. Two complete files would drift.
# ==========================================================

services:
  api:
    # Pull the published image instead of building. This is what turns
    # release.yml's sha tagging into an actual rollback: set IMAGE_TAG to a
    # known-good sha and `up -d` again. Building on the host instead would
    # make the sha tags decorative.
    build: !reset null
    image: ${IMAGE_REPO:-ghcr.io/pranav-1201/ai-code-review-agent}:${IMAGE_TAG:-latest}
    restart: unless-stopped
    # NO published ports, deliberately. The base file publishes 8000:8000 for
    # local development. Keeping that here would put the API — which defaults
    # to unauthenticated — directly on the public internet beside the proxy,
    # bypassing Caddy's TLS and its X-Forwarded-For normalisation, which is
    # what stops a caller forging its own rate-limit bucket. The API is
    # reachable only on the compose network.
    ports: !reset []
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health', timeout=3).status == 200 else 1)"]
      interval: 10s
      timeout: 5s
      retries: 6
      start_period: 20s

  worker:
    build: !reset null
    image: ${IMAGE_REPO:-ghcr.io/pranav-1201/ai-code-review-agent}:${IMAGE_TAG:-latest}
    restart: unless-stopped

  redis:
    restart: unless-stopped

  web:
    image: ${WEB_IMAGE_REPO:-ghcr.io/pranav-1201/ai-code-review-agent-web}:${IMAGE_TAG:-latest}
    restart: unless-stopped
    # SITE_ADDRESS unset -> Caddy binds :80 and serves plain HTTP, so the
    # stack boots anywhere. Set it to a hostname and Caddy obtains a
    # certificate automatically. Port 80 must stay open even when only 443
    # serves traffic: the HTTP-01 challenge uses it.
    environment:
      SITE_ADDRESS: ${SITE_ADDRESS:-}
    ports:
      - "80:80"
      - "443:443"
    volumes:
      # caddy_data holds issued certificates and MUST persist. Without it
      # Caddy re-issues on every restart and will hit Let's Encrypt rate
      # limits.
      - caddy-data:/data
      - caddy-config:/config
    depends_on:
      api:
        condition: service_healthy

  backup:
    image: alpine:3.20
    restart: unless-stopped
    # sqlite installed at start rather than in a custom image: it is one small
    # package and the loop is long-running, so this runs once per container
    # lifetime. A whole Dockerfile for `apk add sqlite` would be more to
    # maintain than it saves.
    command: sh -c "apk add --no-cache sqlite >/dev/null && exec sh /scripts/backup-sqlite.sh"
    environment:
      DB_PATH: /data/scan_states.db
      BACKUP_DIR: /backups
      BACKUP_INTERVAL_SECONDS: ${BACKUP_INTERVAL_SECONDS:-86400}
      BACKUP_KEEP: ${BACKUP_KEEP:-7}
    volumes:
      # Read-only: the backup service must never be able to write the store it
      # is protecting.
      - scan-data:/data:ro
      - ./scripts:/scripts:ro
      # A host bind, not a named volume, on purpose: a backup that lives only
      # inside Docker dies with the Docker state you are most likely to be
      # recovering from.
      #
      # BACKUP_HOST_DIR, not BACKUP_DIR: the two are different paths and giving
      # them one name is how someone sets the host directory and silently
      # changes where the script writes inside the container instead.
      - ${BACKUP_HOST_DIR:-./backups}:/backups

volumes:
  caddy-data:
  caddy-config:
```

- [ ] **Step 2: Verify the file is well-formed YAML without adding a dependency**

`pyyaml` is not a declared dependency (see Global Constraints), so do not import it. Node ships no YAML parser either. Use Python's own tokenizer-free check: confirm the file is at least readable and non-empty, and leave real validation to `docker compose config` in Task 4, which validates the *merged* result and is a strictly better check.

Run:
```bash
test -s docker-compose.prod.yml && grep -c '^  [a-z]' docker-compose.prod.yml
```
Expected: a non-zero count. Real validation happens in Task 4 Step 4.

- [ ] **Step 3: Confirm the `!reset` tag is supported by the operator's Compose version**

`!reset` requires Docker Compose v2.24 or newer. This cannot be checked here (no Docker). Record the requirement so Task 6 documents it, and so a reviewer knows it is a deliberate version floor rather than an accident.

Run:
```bash
grep -n '!reset' docker-compose.prod.yml
```
Expected: two matches on `build:` and one on `ports:`. No action beyond confirming they are present.

- [ ] **Step 4: Commit**

```bash
git add docker-compose.prod.yml
git commit -F - <<'EOF'
Add a production overlay that pulls images instead of building them

Layered onto docker-compose.yml rather than replacing it, so the base file
stays the single description of the stack and this one carries only the
differences.

Pulling by tag is what makes the sha tags release.yml already publishes into
a real rollback: point IMAGE_TAG at a known-good sha and bring the stack up
again. Building on the host would leave those tags decorative.

The API's published port is removed rather than inherited. Keeping it would
expose an API that defaults to unauthenticated directly on the internet,
beside the proxy but not behind it, skipping the header normalisation that
keeps the rate limiter honest.

Backups bind to a host directory because a backup that lives only inside
Docker dies with the Docker state you would be recovering from.
EOF
```

---

### Task 4: CI job that builds the images and boots the stack

This is the task that converts Phase F from "authored" to "verified". It is the reason the phase is worth shipping without Docker locally.

**Files:**
- Modify: `.github/workflows/ci.yml` (append a third job)
- Test: the job itself is the test

**Interfaces:**
- Consumes: `frontend/Dockerfile`, `Caddyfile` (Task 1); `docker-compose.prod.yml` (Task 3).
- Produces: a CI job named `deploy-stack` that must pass before merge.

- [ ] **Step 1: Append the job to `.github/workflows/ci.yml`**

Add after the existing `frontend` job, at the same indentation level (2 spaces under `jobs:`).

```yaml
  deploy-stack:
    name: Deploy stack (build images + boot)
    runs-on: ubuntu-latest
    timeout-minutes: 25

    # This job exists because the development machine has no Docker, so until
    # now nothing in this repository had ever built the images or started the
    # stack — the compose file was authored, reviewed, and shipped unexecuted
    # from Phase B onward. The GitHub runner does have Docker, so the claim
    # can simply be tested instead of deferred to the operator.

    steps:
      - uses: actions/checkout@v4

      - uses: docker/setup-buildx-action@v3

      - name: Build the API image
        uses: docker/build-push-action@v6
        with:
          context: .
          file: backend/Dockerfile
          push: false
          load: true
          tags: local/acra:ci
          cache-from: type=gha
          cache-to: type=gha,mode=max

      - name: Build the web image
        # Context is the repo root, not frontend/, because the Caddyfile lives
        # beside docker-compose.yml. Same convention as backend/Dockerfile.
        uses: docker/build-push-action@v6
        with:
          context: .
          file: frontend/Dockerfile
          push: false
          load: true
          tags: local/acra-web:ci
          build-args: |
            VITE_API_BASE=/api
          cache-from: type=gha
          cache-to: type=gha,mode=max

      - name: Validate the merged compose configuration
        # Renders the base file and the overlay together, resolving variables
        # and every !reset. This is a far stronger check than parsing the
        # overlay alone, and it catches the realistic failure: an overlay that
        # is valid YAML but does not merge.
        env:
          IMAGE_REPO: local/acra
          WEB_IMAGE_REPO: local/acra-web
          IMAGE_TAG: ci
        run: |
          docker compose -f docker-compose.yml -f docker-compose.prod.yml config

      - name: Boot the stack
        env:
          IMAGE_REPO: local/acra
          WEB_IMAGE_REPO: local/acra-web
          IMAGE_TAG: ci
          # Left unset on purpose so Caddy binds :80 and serves plain HTTP.
          # There is no DNS name here and no way to complete an ACME challenge.
          SITE_ADDRESS: ""
          BACKUP_HOST_DIR: ./ci-backups
          # Short enough that the smoke test can observe one snapshot actually
          # being written, rather than only that the container started.
          BACKUP_INTERVAL_SECONDS: "10"
        run: |
          docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
          docker compose -f docker-compose.yml -f docker-compose.prod.yml ps

      - name: Smoke test through the proxy
        run: |
          set -euo pipefail

          # Wait for the edge rather than sleeping a fixed amount: the API
          # healthcheck gates `web`, so this also proves the healthcheck works.
          for i in $(seq 1 60); do
            if curl -fsS -o /dev/null http://localhost/api/health; then
              echo "edge is up after ${i}s"
              break
            fi
            if [ "$i" = "60" ]; then
              echo "edge never came up" >&2
              exit 1
            fi
            sleep 1
          done

          echo "--- GET /api/health (proxied, prefix stripped) ---"
          curl -fsS http://localhost/api/health | tee /tmp/health.json
          echo

          # The prefix strip is the subtle part of the Caddyfile, so assert it
          # rather than assuming: the backend serves /health, and it is only
          # reachable at /api/health if handle_path removed the prefix.
          grep -q '"status"' /tmp/health.json

          echo "--- GET / (SPA shell) ---"
          curl -fsS http://localhost/ | head -c 400
          echo

          # try_files: a deep client-side route has no file on disk and must
          # still return the shell rather than 404.
          echo "--- GET /history/deep-link (client-side route) ---"
          curl -fsS -o /dev/null -w '%{http_code}\n' http://localhost/history/deep-link

      - name: Confirm the API port is NOT published
        # The overlay resets it. If this ever regresses, an unauthenticated
        # API is exposed beside the proxy instead of behind it, which is the
        # single worst outcome available in this stack.
        run: |
          if curl -fsS -o /dev/null --max-time 5 http://localhost:8000/health; then
            echo "FAIL: the API is reachable on :8000; the overlay's port reset regressed" >&2
            exit 1
          fi
          echo "OK: :8000 is not published"

      - name: Confirm a backup snapshot gets written
        run: |
          set -euo pipefail
          # The interval is 10s in this job, so a snapshot should appear
          # quickly. The store is created lazily on first scan, so an empty
          # directory here is a legitimate outcome — assert the service is
          # RUNNING and logging, not that a file exists.
          sleep 15
          docker compose -f docker-compose.yml -f docker-compose.prod.yml logs backup | tail -20
          docker compose -f docker-compose.yml -f docker-compose.prod.yml logs backup | grep -q "backup: started"

      - name: Dump logs on failure
        if: failure()
        run: docker compose -f docker-compose.yml -f docker-compose.prod.yml logs --tail=200

      - name: Tear down
        if: always()
        run: docker compose -f docker-compose.yml -f docker-compose.prod.yml down -v
```

- [ ] **Step 2: Update the workflow's header comment**

The comment block at the top of `ci.yml` lists the checks and says "Backend and frontend are separate jobs". There are now three. Edit the list to add the new job so the file does not describe itself incorrectly.

Add to the check list (after the `playwright test` line):
```
#   docker compose up               images build and the whole stack boots
```

And change the sentence "Backend and frontend are separate jobs so they run in parallel and a frontend-only break is legible at a glance." to name all three jobs.

- [ ] **Step 3: Verify the workflow file is still well-formed**

Run:
```bash
grep -n '^  [a-z-]*:$' .github/workflows/ci.yml
```
Expected: exactly three job keys — `backend:`, `frontend:`, `deploy-stack:` — plus nothing else at that indentation.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/ci.yml
git commit -F - <<'EOF'
Actually boot the stack in CI instead of shipping it unexecuted

Since Phase B the compose stack has been authored, reviewed, and shipped
without ever being run, because the development machine has no Docker. The
GitHub runner does, so this stops being something to defer to the operator.

The job builds both images, renders the merged overlay, brings everything up,
and drives the edge: /api/health proves handle_path strips the prefix, a deep
link proves try_files serves the SPA shell, and a negative check proves the
API is not reachable on 8000 — exposing it beside the proxy rather than
behind it would skip the header normalisation the rate limiter depends on.
EOF
```

---

### Task 5: Publish the web image from release.yml

**Files:**
- Modify: `.github/workflows/release.yml`
- Test: none — the workflow only runs on `main` after CI passes

**Interfaces:**
- Consumes: `frontend/Dockerfile` (Task 1).
- Produces: GHCR tags `ghcr.io/pranav-1201/ai-code-review-agent-web:<sha>` and `:latest`.

- [ ] **Step 1: Add a web-image name output beside the existing one**

In the `Resolve image name` step, the current line produces one name. Add a second output for the web image, derived the same way so the lowercasing logic is not duplicated with a different implementation:

```yaml
      - name: Resolve image name
        # GHCR rejects uppercase in image paths and this repository's owner has
        # capitals, so ${{ github.repository }} cannot be used raw.
        id: img
        run: |
          base="ghcr.io/$(echo '${{ github.repository }}' | tr '[:upper:]' '[:lower:]')"
          echo "name=$base" >> "$GITHUB_OUTPUT"
          echo "web=$base-web" >> "$GITHUB_OUTPUT"
```

- [ ] **Step 2: Add the web build/push step after the existing one**

```yaml
      - name: Build and push the web image
        # The frontend bundle and the API are versioned together and can
        # disagree about request shapes, so a sha-tagged rollback that covered
        # only the API would not be a rollback.
        uses: docker/build-push-action@v6
        with:
          context: .
          file: frontend/Dockerfile
          push: true
          tags: |
            ${{ steps.img.outputs.web }}:${{ steps.sha.outputs.value }}
            ${{ steps.img.outputs.web }}:latest
          build-args: |
            VITE_API_BASE=/api
          # VITE_API_KEY is deliberately absent. A published image is a public
          # artifact and Vite inlines these values into the bundle, so passing
          # a key here would publish the key. A deployment that wants one
          # builds the web image on the host; DEPLOYMENT.md says how.
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

- [ ] **Step 3: Update the workflow header comment**

The header says "One image serves BOTH the api and worker services". That remains true, but there are now two images. Add a sentence naming the web image and why it is tagged in lockstep.

- [ ] **Step 4: Verify**

Run:
```bash
grep -n 'outputs.web\|build-args\|VITE_API_KEY' .github/workflows/release.yml
```
Expected: the web output is defined once and used twice; `build-args` appears once with `VITE_API_BASE=/api`; `VITE_API_KEY` appears only inside the explanatory comment, never as a passed argument.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/release.yml
git commit -F - <<'EOF'
Publish the web image alongside the API image

The frontend bundle and the API it calls are versioned together and can
disagree about request shapes, so tagging only the API by sha would leave
half the deployment unable to roll back with it.

VITE_API_KEY is not passed here. Vite inlines it into the bundle and a
published image is a public artifact, so a key baked in at this step would be
a published key. Deployments that want one build the web image on the host.
EOF
```

---

### Task 6: Documentation — env template and the VPS runbook

**Files:**
- Modify: `.env.example`
- Modify: `DEPLOYMENT.md`
- Modify: `docs/superpowers/specs/2026-08-19-phase-f-deploy-design.md`

**Interfaces:**
- Consumes: every variable name introduced in Tasks 1–5.
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Add a production block to `.env.example`**

Append a new section. Every variable name must match Task 3 exactly.

```
# ----------------------------------------------------------
# Production deployment (Phase F) — see DEPLOYMENT.md
# Only read when the production overlay is in use:
#   docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
# ----------------------------------------------------------

# The public address Caddy serves. UNSET means ":80" — plain HTTP, which is
# right for a laptop and wrong for a server. Set it to a hostname whose DNS
# already points at this host and Caddy obtains a certificate automatically on
# first boot. Ports 80 AND 443 must both be open: the HTTP-01 challenge uses
# 80 even though only 443 serves traffic afterwards.
# SITE_ADDRESS=scan.example.com

# Which published image to run. This is the rollback control: set it to a
# commit sha that GHCR already holds and bring the stack up again.
# IMAGE_TAG=latest

# Override only if you publish to a different registry or fork the repo.
# IMAGE_REPO=ghcr.io/pranav-1201/ai-code-review-agent
# WEB_IMAGE_REPO=ghcr.io/pranav-1201/ai-code-review-agent-web

# Snapshot policy for the scan store. BACKUP_HOST_DIR is a HOST path,
# deliberately: a backup living only inside Docker dies with the Docker state
# you would be recovering from. (The path INSIDE the container is fixed at
# /backups and is not configurable — they are two different paths and sharing
# one name is how you accidentally change the wrong one.)
# BACKUP_HOST_DIR=/var/lib/acra-backups
# BACKUP_INTERVAL_SECONDS=86400
# BACKUP_KEEP=7
```

- [ ] **Step 2: Correct the "every variable is optional" claim in `.env.example`**

The header currently states that every variable is optional and the app boots with all of them unset. That is true for local development and stops being true the moment the host is public. Add one sentence immediately after that paragraph:

```
# That optionality is a LOCAL-DEV property. For an internet-facing deployment
# API_KEY is not optional: /scan runs `git clone` on request, and an unset key
# means anyone who finds the host can spend your disk and bandwidth. /health
# reports "auth": "disabled" so this is visible rather than assumed.
```

- [ ] **Step 3: Fix the stale caveat in `DEPLOYMENT.md`**

Find the bullet in "Known caveats / deferred hardening" beginning "**Clone-cache disk growth**". It claims there is no eviction and calls it an open item. Phase E shipped LRU eviction and a clone-size watchdog, and this same file documents them under "Operations (Phase E) → Disk ceilings" — so the file currently contradicts itself.

Replace that bullet with:

```markdown
- **Disk ceilings are per host, not per deployment.** Phase E added LRU eviction
  across both caches (`MAX_CACHE_MB`) and a clone-size watchdog (`MAX_REPO_MB`);
  see "Operations (Phase E) → Disk ceilings" below for the values and how they
  interact. What remains true is that those ceilings bound the *caches* only:
  the backup directory (Phase F) is outside them and is bounded separately by
  `BACKUP_KEEP`.
```

- [ ] **Step 4: Add the VPS runbook section to `DEPLOYMENT.md`**

Add a new top-level section after "Run the stack". It must contain, in order:

1. **Requirements** — a host with Docker Engine and **Compose v2.24+** (the overlay uses `!reset`, which older versions reject), ports 80 and 443 open, a DNS A record if TLS is wanted.
2. **First deploy** — clone, `cp .env.example .env`, set `API_KEY` (state plainly that leaving it unset exposes `git clone` to the internet) and `SITE_ADDRESS`, then
   `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d`.
3. **Verification checklist**, written as things the operator confirms:
   - `docker compose ... ps` shows `api` healthy, and `web`, `worker`, `redis`, `backup` running.
   - `curl -fsS https://<host>/api/health` returns JSON with `"auth": "enabled"`. If it says `disabled`, `API_KEY` did not reach the container — stop and fix it before announcing the URL.
   - The SPA loads at `https://<host>/`, and a deep link such as `https://<host>/history/x` survives a browser refresh.
   - `curl http://<host>:8000/health` **fails to connect**. Success means the API is exposed beside the proxy rather than behind it.
   - After one interval, `ls $BACKUP_HOST_DIR` on the host contains a `scan-*.db`.
4. **Upgrade** — `IMAGE_TAG=<sha> docker compose ... pull && ... up -d`.
5. **Rollback** — the same command with an earlier sha; note that API and web images share the tag so both move together.
6. **Restore** — point at `scripts/restore-sqlite.sh`, and repeat that the stack must be down first.
7. **What CI proves and what it does not** — state that the `deploy-stack` job builds both images and boots the stack on every push, so "the images build" and "the stack starts" are gated claims; and that TLS issuance, real DNS, and behaviour under load are NOT covered, because the CI job runs on `:80` with no hostname.

- [ ] **Step 5: Correct two details in the spec**

The spec was written before Task 1 and Task 4 settled. Update it so it does not disagree with what shipped:

- §4.1 says a `frontend/.dockerignore` is "required, not optional". With the build context at the repository root, the root `.dockerignore` covers it and no second file was created. Replace that paragraph with the reason the root context was chosen.
- §2 and §6 say image build and stack boot cannot be verified. That was true of the *local machine* and false of CI. Rewrite both to say that the `deploy-stack` job covers them, and narrow the genuinely-unverified list to TLS issuance, real DNS, and load.
- §4.1 says `node:22-alpine`; the implementation uses `node:20-alpine` to match CI. Correct it.

- [ ] **Step 6: Verify the docs do not contradict the implementation**

Run:
```bash
grep -n 'SITE_ADDRESS\|IMAGE_TAG\|IMAGE_REPO\|BACKUP_KEEP\|BACKUP_HOST_DIR\|BACKUP_INTERVAL_SECONDS' .env.example docker-compose.prod.yml DEPLOYMENT.md | sort
```
Expected: every variable named in `docker-compose.prod.yml` also appears in `.env.example`, and no variable appears in `.env.example` that the overlay does not read. A name in one and not the other is the bug this step exists to catch.

Run:
```bash
grep -n 'node:2' frontend/Dockerfile docs/superpowers/specs/2026-08-19-phase-f-deploy-design.md
```
Expected: both say `node:20-alpine`.

- [ ] **Step 7: Commit**

```bash
git add .env.example DEPLOYMENT.md docs/superpowers/specs/2026-08-19-phase-f-deploy-design.md
git commit -F - <<'EOF'
Write the VPS runbook and correct two documents that had gone stale

Adds the first-deploy, upgrade, rollback, and restore procedures, plus a
verification checklist written as things the operator confirms rather than
things this repository asserts.

Two corrections. DEPLOYMENT.md still listed clone-cache growth as having no
eviction, which Phase E shipped and which the same file documents a few
sections further down — it was contradicting itself. And the Phase F spec
claimed the image build and stack boot could not be verified, which was true
of the development machine and false of CI, where they are now gated.
EOF
```

---

## Final verification

After all six tasks, run the full local gate. These are the only claims this machine can support.

- [ ] Backend suite: `.\venv\Scripts\python.exe -m pytest -q` → expected **324 passed**
- [ ] Detector gate: `.\venv\Scripts\python.exe backend/benchmark/run_benchmark.py --gate` → expected exit 0
- [ ] Frontend types: `cd frontend && npx tsc -b` → exit 0
- [ ] Frontend build: `cd frontend && npm run build` → exit 0
- [ ] Frontend units: `cd frontend && npm test` → expected **22 passed**
- [ ] No application code changed: `git diff --stat main -- backend/ frontend/src/` → **empty**

Then push the branch and let CI run. The `deploy-stack` job is the evidence for every claim this machine cannot make. **Do not report Phase F complete until that job is green** — a red `deploy-stack` means the stack does not boot, which is the entire point of the phase.
