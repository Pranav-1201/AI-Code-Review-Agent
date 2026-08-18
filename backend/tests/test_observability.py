"""
Structured logging and error reporting (Phase E — ops hardening).

Before this module the project had zero logging: no getLogger, no
basicConfig, and 189 print() calls. A deployed container emitted
unstructured lines with no level, no timestamp, and no way to correlate two
lines belonging to the same scan.
"""

import json
import logging

import pytest

from backend.app import observability


@pytest.fixture(autouse=True)
def _clean_logging():
    """Each test gets a fresh root logger; handlers are global state."""
    yield
    observability.configure_logging(force=True)


def test_json_format_emits_parseable_records(monkeypatch, capsys):
    monkeypatch.setenv("LOG_FORMAT", "json")
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    observability.configure_logging(force=True)

    observability.get_logger("test.logger").info("scan started")

    payload = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    assert payload["message"] == "scan started"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "test.logger"
    assert payload["scan_id"] is None
    assert payload["timestamp"]


def test_scan_id_is_attached_from_the_contextvar(monkeypatch, capsys):
    monkeypatch.setenv("LOG_FORMAT", "json")
    observability.configure_logging(force=True)

    with observability.scan_context("scan-abc123"):
        observability.get_logger("test.logger").info("cloning")

    payload = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    assert payload["scan_id"] == "scan-abc123"


def test_scan_context_is_cleared_on_exit(monkeypatch):
    observability.configure_logging(force=True)
    with observability.scan_context("scan-abc123"):
        assert observability.current_scan_id() == "scan-abc123"
    assert observability.current_scan_id() is None


def test_scan_context_is_cleared_even_when_the_body_raises(monkeypatch):
    observability.configure_logging(force=True)
    with pytest.raises(ValueError):
        with observability.scan_context("scan-boom"):
            raise ValueError("pipeline blew up")
    assert observability.current_scan_id() is None


def test_configure_logging_is_idempotent(monkeypatch):
    """Calling twice must not double every log line."""
    monkeypatch.setenv("LOG_FORMAT", "json")
    observability.configure_logging(force=True)
    observability.configure_logging()
    observability.configure_logging()

    ours = [h for h in logging.getLogger().handlers
            if getattr(h, "_etproject", False)]
    assert len(ours) == 1


def test_text_format_is_the_default(monkeypatch, capsys):
    monkeypatch.delenv("LOG_FORMAT", raising=False)
    observability.configure_logging(force=True)

    observability.get_logger("test.logger").info("plain line")

    line = capsys.readouterr().err.strip().splitlines()[-1]
    with pytest.raises(json.JSONDecodeError):
        json.loads(line)
    assert "plain line" in line


def test_log_level_is_read_from_env(monkeypatch, capsys):
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    monkeypatch.setenv("LOG_FORMAT", "json")
    observability.configure_logging(force=True)

    observability.get_logger("test.logger").info("should not appear")
    observability.get_logger("test.logger").warning("should appear")

    lines = capsys.readouterr().err.strip().splitlines()
    messages = [json.loads(line)["message"] for line in lines if line]
    assert "should not appear" not in messages
    assert "should appear" in messages


def test_exception_info_is_included(monkeypatch, capsys):
    monkeypatch.setenv("LOG_FORMAT", "json")
    observability.configure_logging(force=True)

    try:
        raise RuntimeError("clone failed")
    except RuntimeError:
        observability.get_logger("test.logger").exception("scan errored")

    payload = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    assert "RuntimeError: clone failed" in payload["exc_info"]
