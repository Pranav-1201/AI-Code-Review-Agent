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
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies first so the (large, slow) ML layer is cached across
# code-only rebuilds. NOTE: requirements.txt pulls torch/transformers/faiss via
# the CPU index at its top, so the first build is multi-GB and slow — expected.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Application code.
COPY . .

# The scan store (progress + result) lives on a volume shared by api + worker.
ENV SCAN_DB_PATH=/data/scan_states.db
EXPOSE 8000

# Default = API. The worker service overrides `command` in docker-compose.yml.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
