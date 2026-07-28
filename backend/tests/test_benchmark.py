"""
Benchmark corpus gate (Phase 6 / Chunk 5).

Runs the FIXTURE half of the benchmark (curated, offline, deterministic) inside
the normal test suite so every release enforces the per-finding-type
precision/recall floor in corpus/thresholds.json. The real-repo half is NOT run
here — it clones pinned public repos over the network and is report-only, so it
must never be able to fail CI.
"""

import sys
from pathlib import Path

import pytest

BENCH = Path(__file__).resolve().parents[1] / "benchmark"
sys.path.insert(0, str(BENCH))

import run_benchmark as rb  # noqa: E402


def test_all_fixtures_discovered():
    names = rb._fixture_names()
    assert len(names) == 8, names
    assert all(n.startswith("f") for n in names), names


def test_fixture_gate_passes():
    """No per-type precision/recall may drop below the recorded baseline."""
    fx = rb.run_fixtures()
    thresholds = rb.load_json(rb.CORPUS / "thresholds.json")
    failures = []
    for t, c in fx.items():
        prec, rec = rb._pr(c)
        th = thresholds.get(t, {"precision": 0.0, "recall": 0.0})
        if prec < th["precision"] - 1e-9 or rec < th["recall"] - 1e-9:
            failures.append((t, round(prec, 3), round(rec, 3), th))
    assert not failures, f"benchmark regression: {failures}"


def test_clean_types_have_no_false_positives():
    """Types that are supposed to be perfect must not start crying wolf."""
    fx = rb.run_fixtures()
    for t in ("dangerous_function", "sql_injection", "hardcoded_credential",
              "weak_crypto", "race_condition", "insecure_config",
              "dead_import", "high_complexity"):
        assert fx[t]["fp"] == 0, (t, dict(fx[t]))


def test_recall_is_perfect_where_expected():
    """Every planted true positive for the strong types is actually found."""
    fx = rb.run_fixtures()
    for t in ("dangerous_function", "command_injection", "sql_injection",
              "hardcoded_credential", "dead_import", "dead_function",
              "high_complexity"):
        assert fx[t]["fn"] == 0, (t, dict(fx[t]))


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
