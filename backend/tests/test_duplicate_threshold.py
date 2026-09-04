"""Backlog B5 — justify or move the duplicate-similarity threshold.

The audit's worry was that 30% was too low and let noise through. Measured,
the opposite is true: across this repository (246 files) and the one other
real clone available (43 files), the highest-scoring pair of ANY two files
was 19%. At a 30% floor the block-similarity detector reported nothing at
all, on either repository.

The 19% pair is a genuine near-duplicate — phase4_validation.py and
phase5_validation.py share a copy-pasted result harness, 29% of the smaller
file's unique significant lines. So the floor was not filtering noise; it was
sitting above every real finding.

The metric is strict by construction: similarity is shared sliding-windows
over the *smaller* file's total windows, so 30% means nearly a third of a
file is duplicated verbatim. 15% is the calibrated floor — it admits the
validation-script pair and still excludes the 11% shadcn boilerplate pair
(sidebar.tsx / toggle.tsx), which is the nearest thing to a false positive
in the measured set.

Calibration rests on two repositories. That is thin, and the constant is
named and documented so the next person can move it with evidence rather
than guessing at a bare literal.
"""
from backend.app.analysis.duplicate_detector import (
    MIN_BLOCK_SIMILARITY_PERCENT,
    detect_duplicates,
)

# A copy-pasted harness, of the kind the validation scripts actually share.
_HARNESS = "\n".join([
    "def record(item_id, ok):",
    "    _RESULTS.append((item_id, ok))",
    "    if not ok:",
    "        print('FAIL', item_id)",
    "    return ok",
    "",
    "def summarize():",
    "    passed = sum(1 for _, ok in _RESULTS if ok)",
    "    total = len(_RESULTS)",
    "    print('RESULT:', passed, '/', total)",
    "    return passed == total",
])


def _file(path, body):
    return {"file_path": path, "file_name": path, "content": body}


def test_the_threshold_is_a_named_constant_not_a_literal():
    assert isinstance(MIN_BLOCK_SIMILARITY_PERCENT, int)
    assert 0 < MIN_BLOCK_SIMILARITY_PERCENT < 100


def test_a_copy_pasted_harness_is_reported():
    """At the old 30% floor this pair scored below the line and vanished."""
    unique_a = "\n".join(f"    step_a_{i} = compute_{i}(payload)" for i in range(14))
    unique_b = "\n".join(f"    step_b_{i} = derive_{i}(payload)" for i in range(14))
    files = [
        _file("phase_a.py", _HARNESS + "\n\ndef run_a(payload):\n" + unique_a + "\n"),
        _file("phase_b.py", _HARNESS + "\n\ndef run_b(payload):\n" + unique_b + "\n"),
    ]
    pairs = detect_duplicates(files)
    assert pairs, "a shared copy-pasted harness must be reported"
    assert pairs[0]["similarity"] >= MIN_BLOCK_SIMILARITY_PERCENT


def test_two_unrelated_files_are_not_reported():
    files = [
        _file("a.py", "\n".join(f"    alpha_{i} = one_{i}(x)" for i in range(30))),
        _file("b.py", "\n".join(f"    beta_{i} = two_{i}(y)" for i in range(30))),
    ]
    assert detect_duplicates(files) == []


def test_an_identical_file_pair_is_still_reported_as_exact():
    body = _HARNESS + "\n\ndef run(payload):\n    return payload\n"
    pairs = detect_duplicates([_file("a.py", body), _file("b.py", body)])
    assert pairs
    assert pairs[0]["similarity"] == 100


def test_nothing_below_the_threshold_is_ever_returned():
    files = [
        _file("a.py", _HARNESS + "\n" + "\n".join(
            f"    filler_a_{i} = f_{i}(x)" for i in range(200))),
        _file("b.py", _HARNESS + "\n" + "\n".join(
            f"    filler_b_{i} = g_{i}(y)" for i in range(200))),
    ]
    for pair in detect_duplicates(files):
        assert pair["similarity"] >= MIN_BLOCK_SIMILARITY_PERCENT
