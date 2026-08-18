# ==========================================================
# Single image for BOTH the API and the Celery worker (same code, the compose
# service picks the command). Phase 6 / Chunk 5.
# Build context is the REPO ROOT (see docker-compose.yml), not backend/, because
# the app entrypoint is repo-root main.py.
# ==========================================================
FROM python:3.11-slim

# git is a RUNTIME dependency: the worker clones/fetches repositories to scan
# (main.run_scan_pipeline shells out to `git clone`/`git fetch`).
RUN apt-get update \
 && apt-get install -y --no-install-recommends git \
 && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    LOG_FORMAT=json

WORKDIR /app

# Install dependencies first so the dependency layer is cached across
# code-only rebuilds.
#
# Installs from requirements.lock, NOT requirements.txt: the loose file would
# let a transitive release change what ships between two builds of the same
# commit.
#
# Phase E: the ML stack (torch, transformers, sentence-transformers, faiss)
# moved to requirements-ml.lock and is deliberately NOT installed here. No
# shipped configuration could reach it — rag/faiss_index/ is gitignored, so
# retrieval always took its no-index fallback, and ENABLE_CODEBERT defaults
# to false. The image was paying gigabytes for code that could not run. The
# base lock dropped from 282 to 163 pinned packages as a result, and the
# multi-GB CPU-torch wheel is gone with it.
#
# A deployment that genuinely wants CodeBERT scoring or FAISS retrieval (and
# ships an index) adds a second install line for requirements-ml.lock.
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock

# Application code.
COPY . .

# The scan store (progress + result) lives on a volume shared by api + worker.
ENV SCAN_DB_PATH=/data/scan_states.db
EXPOSE 8000

# Default = API. The worker service overrides `command` in docker-compose.yml.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
