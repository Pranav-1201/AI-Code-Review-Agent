# ==========================================================
# File: backend/validation/phase0_1_validation.py
# Purpose: Chunk 0 regression harness. Pins the Phase 0/1
#          fixes and the two Chunk 0 regression repairs so
#          they can never silently reappear.
#
# Run:  python backend/validation/phase0_1_validation.py
# Exit: 0 if every check passes, 1 otherwise.
#
# Covers audit items: 1, 2, 4, 5, 11, and Defects A, B, C.
# Each check prints the OBSERVED values it asserts on, so the
# output is evidence, not a bare "ok".
#
# SECURITY NOTE: some checks embed vulnerable snippets as string
# literals (eval(cmd), os.system(cmd), subprocess.run(cmd, shell=True)).
# These are deliberate fixtures written to a temp dir and fed to the
# analyzer to prove it DETECTS them. This harness never executes them.
# ==========================================================

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

# Allow running directly: put repo root (parent of backend/) on sys.path
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


# ----------------------------------------------------------
# Tiny check harness
# ----------------------------------------------------------

_RESULTS: list[tuple[str, bool, str]] = []


def check(item_id: str, description: str):
    """Decorator: run a check fn, capture PASS/FAIL + its printed evidence."""
    def wrap(fn):
        print(f"\n[{item_id}] {description}")
        try:
            detail = fn()
            _RESULTS.append((item_id, True, detail or ""))
            print(f"    PASS  {detail or ''}")
        except AssertionError as e:
            _RESULTS.append((item_id, False, str(e)))
            print(f"    FAIL  {e}")
        except Exception as e:  # unexpected crash == failed check
            _RESULTS.append((item_id, False, f"{type(e).__name__}: {e}"))
            print(f"    ERROR {type(e).__name__}: {e}")
        return fn
    return wrap


def _write(dirpath: Path, name: str, code: str) -> Path:
    p = dirpath / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(code, encoding="utf-8")
    return p


# ==========================================================
# Item 1 — CodeBERT gated + deterministic probability
# ==========================================================

@check("1", "CodeBERT is gated OFF by default; probability is deterministic + reproducible")
def _item1():
    from backend.app.services import llm_service

    assert llm_service.ENABLE_CODEBERT is False, \
        f"ENABLE_CODEBERT must default False, got {llm_service.ENABLE_CODEBERT!r}"

    # Pure function: same signals -> same probability (no randomness)
    p_clean = llm_service._compute_deterministic_probability(cc=1, depth=0, sec_issues=[], line_count=10)
    p_clean2 = llm_service._compute_deterministic_probability(cc=1, depth=0, sec_issues=[], line_count=10)
    assert p_clean == p_clean2, "deterministic probability is not reproducible"

    # Scales with real signals: complex + critical > clean
    p_bad = llm_service._compute_deterministic_probability(
        cc=15, depth=3, sec_issues=[{"severity": "Critical"}, {"severity": "Critical"}], line_count=600
    )
    assert p_bad > p_clean, f"probability must scale with signals: bad={p_bad} clean={p_clean}"

    # End-to-end reproducibility: same code analysed twice -> identical score
    code = "def f(x):\n    if x:\n        return 1\n    return 2\n"
    s1 = llm_service.analyze_code(code, language="python", security_issues=[])["code_quality_score"]
    s2 = llm_service.analyze_code(code, language="python", security_issues=[])["code_quality_score"]
    assert s1 == s2, f"analyze_code not reproducible: {s1} vs {s2} (raw classifier leak?)"

    return f"clean={p_clean} bad={p_bad} repro_score={s1}"


# ==========================================================
# Item 2 — is_outdated performs a real PEP 440 compare + TTL cache
# ==========================================================

@check("2", "is_outdated uses real semver compare (not hardcoded False) + TTL cache")
def _item2():
    from backend.app.analysis import dependency_analyzer as da

    # Real comparison semantics
    assert da._is_version_outdated("1.0.0", "2.0.0") is True, "1.0.0 < 2.0.0 must be outdated"
    assert da._is_version_outdated("2.0.0", "2.0.0") is False, "equal versions not outdated"
    assert da._is_version_outdated("2.1.0", "2.0.0") is False, "newer local not outdated"
    assert da._is_version_outdated("unknown", "2.0.0") is False, "unpinned must be skipped"

    # TTL cache exists and is honoured (seed it, then no network should be hit)
    assert da._CACHE_TTL_SECONDS >= 60, "cache TTL missing/too small"
    da._PYPI_VERSION_CACHE["totally-fake-pkg"] = {"latest": "9.9.9", "fetched_at": time.time()}
    assert da._fetch_latest_pypi_version("totally-fake-pkg") == "9.9.9", "TTL cache not used"

    # analyze_dependencies enriches is_outdated (monkeypatch fetch -> no network)
    d = Path(tempfile.mkdtemp())
    _write(d, "requirements.txt", "requests==1.0.0\n")
    orig = da._fetch_latest_pypi_version
    da._fetch_latest_pypi_version = lambda name: "2.32.0"
    try:
        deps = da.analyze_dependencies(str(d))
    finally:
        da._fetch_latest_pypi_version = orig
    req = next(x for x in deps if x["name"] == "requests")
    assert req["is_outdated"] is True, f"requests 1.0.0 vs 2.32.0 must be outdated, got {req}"
    assert req["latest_version"] == "2.32.0", req

    return f"1.0.0<2.0.0=True, equal=False, enriched is_outdated={req['is_outdated']}"


# ==========================================================
# Item 4 — complexity aggregation regression (the Chunk 0 repair)
# ==========================================================

@check("4", "complexity: files WITH functions get real CC; module-only=1.0; syntax-error no crash")
def _item4():
    from backend.app.services import repo_analyzer as ra

    d = Path(tempfile.mkdtemp())

    # (a) file WITH functions -> real averaged CC, not 0
    p = _write(d, "withfns.py",
               "def a(x):\n    if x: return 1\n    return 2\ndef b(y):\n    for i in y:\n        if i: pass\n")
    r = ra._analyze_file_worker((p, d))
    assert r["cyclomatic_complexity"] > 1.0, f"functions must yield real CC, got {r['cyclomatic_complexity']}"
    assert r["max_cyclomatic_complexity"] >= 2, r
    with_cc = r["cyclomatic_complexity"]

    # (b) module-only file -> baseline 1.0 (no NameError)
    p = _write(d, "moduleonly.py", "X = 1\nY = 2\nimport os\n")
    r = ra._analyze_file_worker((p, d))
    assert r["cyclomatic_complexity"] == 1.0, f"module-only must be 1.0, got {r['cyclomatic_complexity']}"

    # (c) syntax-error file -> no crash, doc_coverage stays a tuple-unpacked value
    p = _write(d, "broken.py", "def oops(:\n    pass\n")
    r = ra._analyze_file_worker((p, d))
    assert r is not None and r["documentation_coverage"] == 0.0, "syntax-error file must not crash"

    # direct compute_doc_coverage returns a 2-tuple even on SyntaxError
    cov = ra.compute_doc_coverage("def bad(:\n", "Python")
    assert isinstance(cov, tuple) and len(cov) == 2, f"compute_doc_coverage must return 2-tuple, got {cov!r}"

    return f"withfns cc={with_cc}, module-only=1.0, syntax-error safe, doc_cov tuple={cov}"


# ==========================================================
# Item 5 — scan state persists to SQLite across a restart
# ==========================================================

@check("5", "scan state persists to SQLite and survives a simulated process restart")
def _item5():
    from backend.app.services import scan_manager as sm

    db_path = os.path.join(tempfile.mkdtemp(), "scan_states.db")
    sm._DB_PATH = db_path
    sm._conn = None  # force fresh connection to our temp db

    scan_id = sm.create_scan("https://example.com/repo.git")
    sm.update_scan(scan_id, "analyzing", 42, stage="analysis", stage_detail="halfway", total_files=7)

    # Simulate a process restart: drop the connection, reopen the same file
    sm._conn = None
    restored = sm.get_scan(scan_id)
    assert restored is not None, "scan lost after simulated restart"
    assert restored["progress"] == 42, f"progress not persisted: {restored['progress']}"
    assert restored["status"] == "analyzing", restored
    assert restored["total_files"] == 7, restored

    sm.complete_scan(scan_id, {"health_score": 88})
    sm._conn = None
    done = sm.get_scan(scan_id)
    assert done["status"] == "complete" and done["result"]["health_score"] == 88, done

    return f"persisted progress=42 across restart; completed result={done['result']}"


# ==========================================================
# Item 11 — shell=True produces exactly ONE finding (no duplicate)
# ==========================================================

@check("11", "subprocess.run(cmd, shell=True) yields exactly ONE High command-injection finding")
def _item11():
    from backend.app.services.security_analyzer import detect_security_issues

    code = "import subprocess\nsubprocess.run(cmd, shell=True)\n"
    issues = detect_security_issues(code)
    cmd_inj = [i for i in issues if i.get("severity") == "High"
               and "injection" in i.get("description", "").lower()]
    assert len(cmd_inj) == 1, f"expected exactly 1 High command-injection finding, got {len(cmd_inj)}: {cmd_inj}"

    # And no two findings share the same (line, description) — general dedup guard
    seen = [(i["line"], i["description"]) for i in issues]
    assert len(seen) == len(set(seen)), f"duplicate findings on same node: {seen}"

    return f"{len(cmd_inj)} finding, total issues={len(issues)}, no duplicates"


# ==========================================================
# Defect A — health score uses real production files (not constant)
# ==========================================================

@check("A", "health score counts production files and responds to content (not a constant)")
def _defect_a():
    from backend.app.services.repo_analyzer import analyze_repository
    from backend.app.services.repository_review_engine import RepositoryReviewEngine

    def build(insecure: bool) -> str:
        d = Path(tempfile.mkdtemp())
        _write(d, "util.py", 'def add(a, b):\n    """Add."""\n    return a + b\n')
        body = ("import os\ndef run(cmd):\n    os.system(cmd)\n    eval(cmd)\n"
                if insecure else
                'def mul(a, b):\n    """Mul."""\n    return a * b\n')
        _write(d, "core.py", body)
        _write(d, "tests/test_util.py", "def test_add():\n    assert 1 + 1 == 2\n")
        return str(d)

    clean = RepositoryReviewEngine().review_repository(build(False), analyze_repository(build(False)))
    dirty = RepositoryReviewEngine().review_repository(build(True), analyze_repository(build(True)))
    cs, ds = clean["repository_summary"], dirty["repository_summary"]

    assert cs["production_files"] == 2, f"production files miscounted: {cs['production_files']}"
    assert cs["average_quality_score"] > 0, "avg quality score is 0 (prod filter broken)"
    assert 0 < cs["health_score"] <= 100, f"health out of range: {cs['health_score']}"
    assert ds["total_security_issues"] >= 2, f"insecure repo security not counted: {ds}"
    # Responsiveness: an insecure repo must score strictly lower than a clean one
    assert ds["health_score"] < cs["health_score"], \
        f"health not responsive to content: clean={cs['health_score']} dirty={ds['health_score']}"

    return f"clean health={cs['health_score']} (prod={cs['production_files']}), dirty health={ds['health_score']}"


# ==========================================================
# Defect B — is_test is wired from repo_analyzer through the engine
# ==========================================================

@check("B", "is_test flows: test files flagged True, production files False")
def _defect_b():
    from backend.app.services.repo_analyzer import analyze_repository

    d = Path(tempfile.mkdtemp())
    _write(d, "app.py", "def handler():\n    return 1\n")
    _write(d, "tests/test_app.py", "def test_handler():\n    assert True\n")
    files = {f["file_name"]: f for f in analyze_repository(str(d))}

    assert files["test_app.py"]["is_test"] is True, "test file must be is_test=True"
    assert files["test_app.py"]["file_type"] == "test", files["test_app.py"]
    assert files["app.py"]["is_test"] is False, "production file must be is_test=False"
    return "test_app.py is_test=True, app.py is_test=False"


# ==========================================================
# Defect C — file_role is distinct from file_type AND changes behavior
# ==========================================================

@check("C", "file_role is a distinct fine role and drives role-aware complexity thresholds")
def _defect_c():
    from backend.app.services.repo_analyzer import analyze_repository
    from backend.app.analysis.complexity_analyzer import ComplexityAnalyzer

    # (1) coarse file_type and fine file_role are separate fields
    d = Path(tempfile.mkdtemp())
    cli_body = "import click\n" + "".join(
        f"def cmd_{i}():\n    return {i}\n" for i in range(12)
    )
    _write(d, "cli.py", cli_body)
    f = {x["file_name"]: x for x in analyze_repository(str(d))}["cli.py"]
    assert f["file_type"] == "production", f"coarse type should be production, got {f['file_type']}"
    assert f["file_role"] == "cli_parser", f"fine role should be cli_parser, got {f['file_role']}"

    # (2) the role actually changes the verdict at the same complexity
    ca = ComplexityAnalyzer()
    cc = 15
    util_risk = ca.get_risk_level(cc, role="utility")        # utility warn=10 -> warning
    orch_risk = ca.get_risk_level(cc, role="orchestrator")   # orchestrator warn=25 -> ok
    assert util_risk != orch_risk, f"role must change risk verdict: util={util_risk} orch={orch_risk}"
    assert util_risk == "warning" and orch_risk == "ok", f"util={util_risk} orch={orch_risk}"

    return f"file_type=production / file_role=cli_parser; cc=15 util={util_risk}, orch={orch_risk}"


# ==========================================================
# Summary
# ==========================================================

def main() -> int:
    print("=" * 62)
    print("Chunk 0 validation - items 1, 2, 4, 5, 11 + Defects A, B, C")
    print("=" * 62)

    # Checks self-run via the @check decorator at import/def time.
    passed = sum(1 for _, ok, _ in _RESULTS if ok)
    total = len(_RESULTS)

    print("\n" + "=" * 62)
    print(f"RESULT: {passed}/{total} checks passed")
    for item_id, ok, detail in _RESULTS:
        print(f"  [{'PASS' if ok else 'FAIL'}] item {item_id}")
    print("=" * 62)

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
