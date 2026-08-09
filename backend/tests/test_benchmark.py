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


# ----------------------------------------------------------
# Honesty of the reported numbers (Phase C).
# ----------------------------------------------------------
#
# A benchmark that reports a score it did not measure is worse than one that
# reports nothing: it launders "we tested nothing" into "we scored 1.00". The
# harness did exactly that — both pinned clones failed, every counter stayed at
# zero, and it printed "REAL-REPO OVERALL: precision 1.00 recall 1.00
# (TP 0, FP 0, FN 0)". Two independent causes, one test each.


def test_undefined_precision_is_not_reported_as_perfect():
    """An empty counter has NO precision/recall — it must not claim 1.00.

    _pr divided by (tp+fp) and (tp+fn) and fell back to 1.0 when both were
    zero, so a finding type that was never exercised looked flawless.

    Would fail if: the zero-denominator fallback returns a number again, which
    is how a silently-empty corpus starts advertising a perfect score.
    """
    prec, rec = rb._pr({"tp": 0, "fp": 0, "fn": 0})
    assert prec is None, f"undefined precision reported as {prec!r}"
    assert rec is None, f"undefined recall reported as {rec!r}"


def test_real_measurements_still_produce_numbers():
    """The None-for-undefined rule must not swallow genuine scores."""
    prec, rec = rb._pr({"tp": 3, "fp": 1, "fn": 1})
    assert prec == pytest.approx(0.75)
    assert rec == pytest.approx(0.75)


def test_partial_clone_is_not_mistaken_for_a_usable_checkout(tmp_path):
    """A directory containing an empty .git is not a repository.

    The cache was only checked with `(dest / ".git").is_dir()`. A clone that
    died partway leaves exactly that — a .git directory with no objects — so
    the harness skipped re-cloning forever and every later run failed on
    `git rev-parse HEAD`. The cache had no way to heal.

    Would fail if: the validity check goes back to testing for mere existence,
    which silently reintroduces a permanently poisoned cache.
    """
    dest = tmp_path / "flask"
    (dest / ".git").mkdir(parents=True)
    assert rb._is_valid_clone(dest) is False

    assert rb._is_valid_clone(tmp_path / "never-cloned") is False


def test_read_only_files_do_not_block_cache_removal(tmp_path):
    """Purging a cached clone must survive read-only files.

    git marks pack files read-only, and on Windows shutil.rmtree then raises
    PermissionError [WinError 5]. With ignore_errors=True that failure is
    swallowed, the directory survives, and the follow-up `git clone` dies with
    exit 128 on a non-empty destination — so the cache still never heals, just
    with a more confusing error than before.

    Would fail if: the remover goes back to plain rmtree (raises) or to
    ignore_errors=True (silently leaves the directory behind).
    """
    import os
    import stat

    doomed = tmp_path / "cached"
    (doomed / ".git" / "objects").mkdir(parents=True)
    pack = doomed / ".git" / "objects" / "pack.idx"
    pack.write_bytes(b"x")
    os.chmod(pack, stat.S_IREAD)

    rb._force_rmtree(doomed)
    assert not doomed.exists(), "read-only content survived the purge"


def test_skipped_real_repos_are_reported_not_swallowed(monkeypatch):
    """run_real must say which repos it could not measure.

    It caught the clone failure, printed a [warn] into a wall of output, and
    returned an aggregate indistinguishable from a clean run.

    Would fail if: the skip list is dropped again, leaving the caller unable to
    tell "measured nothing" from "measured perfectly".
    """
    def always_fails(entry):
        raise RuntimeError("network down")

    monkeypatch.setattr(rb, "_ensure_clone", always_fails)
    agg, skipped = rb.run_real()

    assert skipped, "clone failures vanished from the result"
    assert not agg, f"skipped repos still produced counters: {dict(agg)}"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
