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
