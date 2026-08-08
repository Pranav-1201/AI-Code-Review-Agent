"""
Live scan-progress stream (Chunk 6 / Item E).

The frontend can subscribe to a scan over Server-Sent Events instead of polling
GET /scan/{id} every 2s. These tests pin the SSE contract on the paths that are
deterministic (no timing): (1) a completed scan streams a single terminal
`complete` frame carrying the full result and then closes, (2) an errored scan
streams a terminal `error` frame with the real reason, and (3) an unknown
scan_id streams an `error` frame. The endpoint is additive — the polling route
is covered elsewhere and left untouched.

The in-flight/progressive path is intentionally NOT tested here: it depends on a
background task advancing the store over time and would either hang the stream
or be timing-flaky. Field content per frame is the same dict GET /scan/{id}
returns, which is already covered by the scan_manager tests.
"""

import json

from fastapi.testclient import TestClient

import backend.app.services.scan_manager as sm
import main

# Reuse the isolated-DB + completed-scan helpers from the history tests so the
# two SSE-relevant fixtures stay in one place.
from backend.tests.test_scan_history import _fresh_db, _complete


def _collect_sse(resp, max_events=10):
    """Parse an SSE response body into a list of decoded `data:` payloads.

    Blank line = event boundary; leading-':' lines are comments (heartbeats)
    and are ignored. Stops after max_events as a safety valve.
    """
    events = []
    data_lines = []
    for line in resp.iter_lines():
        if line == "":
            if data_lines:
                events.append(json.loads("".join(data_lines)))
                data_lines = []
                if len(events) >= max_events:
                    break
            continue
        if line.startswith(":"):
            continue
        if line.startswith("data:"):
            data_lines.append(line[len("data:"):].lstrip())
    if data_lines:  # flush a final frame delivered without a trailing blank line
        events.append(json.loads("".join(data_lines)))
    return events


def test_stream_completed_scan_emits_terminal_result(monkeypatch):
    _fresh_db(monkeypatch)
    sid = _complete("https://github.com/acme/api", health=88, files=5,
                    issues_per_file=[2, 1])

    with TestClient(main.app) as client:
        with client.stream("GET", f"/scan/{sid}/stream") as resp:
            assert resp.status_code == 200
            assert resp.headers["content-type"].startswith("text/event-stream")
            events = _collect_sse(resp)

    terminal = [e for e in events if e.get("status") == "complete"]
    assert terminal, f"expected a complete frame, got {events}"
    result = terminal[-1]["result"]
    assert result["repository_summary"]["health_score"] == 88


def test_stream_errored_scan_emits_reason(monkeypatch):
    _fresh_db(monkeypatch)
    sid = sm.create_scan("failed")
    sm.complete_scan(sid, {"error": "clone failed"})

    with TestClient(main.app) as client:
        with client.stream("GET", f"/scan/{sid}/stream") as resp:
            assert resp.status_code == 200
            events = _collect_sse(resp)

    terminal = [e for e in events if e.get("status") == "error"]
    assert terminal, f"expected an error frame, got {events}"
    assert terminal[-1].get("error") == "clone failed"


def test_stream_unknown_scan_emits_error(monkeypatch):
    _fresh_db(monkeypatch)

    with TestClient(main.app) as client:
        with client.stream("GET", "/scan/does-not-exist/stream") as resp:
            assert resp.status_code == 200
            events = _collect_sse(resp)

    assert events, "expected at least one frame"
    assert events[0].get("status") == "error"
    assert "not found" in events[0].get("error", "").lower()


if __name__ == "__main__":
    import sys
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
