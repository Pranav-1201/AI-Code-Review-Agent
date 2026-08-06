# ==========================================================
# File: queue_roundtrip.py
# Purpose: Prove real OUT-OF-PROCESS Celery dispatch without Docker/Redis
#          (Phase 6 / Chunk 5 release evidence).
# ==========================================================
#
# The test suite proves the EAGER (in-process) path. This proves the other half:
# that a task genuinely travels through a broker to a SEPARATE worker process.
# It uses Kombu's FILESYSTEM broker (messages are files in a shared folder) so no
# Redis is needed, then spawns a real `celery ... worker` subprocess, enqueues a
# task, and confirms the marker the task writes carries a DIFFERENT pid than this
# driver — i.e. the work ran in another process, dispatched over the broker.
#
# This stands in for `docker-compose up` in environments without Docker. The
# production path (Redis broker, prefork/billiard worker) is verified by the user
# per DEPLOYMENT.md. Run:  python backend/queue_roundtrip.py
#
# The worker uses the `solo` pool here purely for cross-platform reliability of
# the evidence run; the containerized worker uses prefork (billiard) — see
# DEPLOYMENT.md.

import os
import sys
import json
import time
import glob
import shutil
import tempfile
import subprocess

from celery import Celery

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUN_DIR = os.environ.get("QRT_DIR") or os.path.join(tempfile.gettempdir(), "etproject_qrt")

_IN = os.path.join(RUN_DIR, "messages")   # producer out == consumer in (rendezvous)
_CTRL = os.path.join(RUN_DIR, "control")
_PROC = os.path.join(RUN_DIR, "processed")
MARKER = os.path.join(RUN_DIR, "marker.json")

for _d in (_IN, _CTRL, _PROC):
    os.makedirs(_d, exist_ok=True)

app = Celery("qrt")
app.conf.update(
    broker_url="filesystem://",
    broker_transport_options={
        "data_folder_in": _IN,
        "data_folder_out": _IN,
        "control_folder": _CTRL,
        "processed_folder": _PROC,
        "store_processed": True,
    },
    task_always_eager=False,          # we WANT real dispatch here
    worker_prefetch_multiplier=1,
)


@app.task(name="qrt.ping")
def ping(token):
    """Runs in the WORKER process; records its pid so the driver can compare."""
    with open(MARKER, "w") as f:
        json.dump({"pid": os.getpid(), "token": token}, f)
    return os.getpid()


def _clear_stale():
    for f in glob.glob(os.path.join(_IN, "*")):
        try:
            os.remove(f)
        except OSError:
            pass
    if os.path.exists(MARKER):
        os.remove(MARKER)


def main():
    driver_pid = os.getpid()
    _clear_stale()

    env = dict(os.environ)
    env["QRT_DIR"] = RUN_DIR
    env["PYTHONPATH"] = REPO_ROOT + os.pathsep + env.get("PYTHONPATH", "")
    # This standalone app uses its own filesystem broker; don't let the product
    # Redis broker env leak in.
    env.pop("CELERY_BROKER_URL", None)
    env.pop("CELERY_RESULT_BACKEND", None)

    print(f"[driver] pid={driver_pid}")
    print(f"[driver] run dir: {RUN_DIR}")
    print("[driver] starting worker subprocess (filesystem broker, solo pool)...")

    worker = subprocess.Popen(
        [sys.executable, "-m", "celery", "-A", "backend.queue_roundtrip.app",
         "worker", "--loglevel=info", "--concurrency=1", "-P", "solo"],
        cwd=REPO_ROOT, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )

    try:
        token = f"rt-{driver_pid}"
        print(f"[driver] enqueuing qrt.ping(token={token}) via the broker...")
        app.send_task("qrt.ping", args=[token])

        deadline = time.time() + 45
        while time.time() < deadline:
            if os.path.exists(MARKER):
                break
            if worker.poll() is not None:
                print("[driver] FAIL: worker exited before handling the task")
                break
            time.sleep(0.5)

        ok = False
        if os.path.exists(MARKER):
            with open(MARKER) as f:
                data = json.load(f)
            worker_pid = data.get("pid")
            same_token = data.get("token") == token
            different_process = worker_pid != driver_pid
            print(f"[driver] marker: {data}")
            print(f"[driver] token matched      = {same_token}")
            print(f"[driver] ran in other pid   = {different_process} "
                  f"(worker={worker_pid} vs driver={driver_pid})")
            ok = same_token and different_process
        else:
            print("[driver] FAIL: no marker written within timeout")
    finally:
        worker.terminate()
        try:
            out, _ = worker.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            worker.kill()
            out, _ = worker.communicate()

    # Surface the worker's own log lines proving it received + ran the task.
    print("\n----- worker log (filtered) -----")
    for line in (out or "").splitlines():
        if any(k in line for k in ("ready", "Received task", "succeeded",
                                   "qrt.ping", "celery@")):
            print("  " + line.strip())
    print("----- end worker log -----\n")

    print("ROUND-TRIP RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
