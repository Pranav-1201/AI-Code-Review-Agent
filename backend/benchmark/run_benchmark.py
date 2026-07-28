#!/usr/bin/env python
# ==========================================================
# File: backend/benchmark/run_benchmark.py
# Purpose (Phase 6 / Chunk 5): the benchmark corpus harness.
#
# Measures PRECISION and RECALL PER FINDING TYPE for the DETERMINISTIC finding
# engines only (security analyzer, dead-code, complexity incl. tree-sitter JS/TS,
# and interprocedural taint) — never the LLM layer, whose output is not
# reproducible and therefore cannot gate a release.
#
# Two corpora, two roles:
#   * FIXTURES  — curated repos with planted, exactly-known ground truth AND
#     decoys (things that look flaggable but must not be). This is the
#     DETERMINISTIC RELEASE GATE: `--gate` exits non-zero if any per-type
#     precision/recall drops below the recorded baseline in thresholds.json.
#   * REAL REPOS — pinned public repos (flask=clean anchor, bottle=organic-mess
#     anchor), SPOT-LABELLED on a hand-verified subset. REPORT-ONLY: a pinned
#     clone is a network dependency and must never fail CI, but its numbers are
#     printed PROMINENTLY (their own section) because that is the figure a
#     portfolio reviewer actually reads.
#
# Usage:
#   python backend/benchmark/run_benchmark.py            # fixtures + real, report
#   python backend/benchmark/run_benchmark.py --gate     # fixtures gate (exit!=0 on regression)
#   python backend/benchmark/run_benchmark.py --no-real  # skip the network clone
#   python backend/benchmark/run_benchmark.py --dump     # dump raw findings per repo
# ==========================================================

import argparse
import json
import os
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.app.services.repo_analyzer import analyze_repository
from backend.app.services.security_analyzer import detect_security_issues
from backend.app.analysis.taint_analyzer import propagate_interprocedural_taint

HERE = Path(__file__).resolve().parent
CORPUS = HERE / "corpus"
FIXTURES = CORPUS / "fixtures"
CLONE_CACHE = Path(tempfile.gettempdir()) / "etproject_benchmark_repos"

# Analyzer issue_type string -> benchmark finding-type slug.
SEC_TYPE_MAP = {
    "Dangerous Function": "dangerous_function",
    "Command Injection": "command_injection",
    "Unsafe Deserialization": "unsafe_deserialization",
    "SQL Injection": "sql_injection",
    "Hardcoded Credential": "hardcoded_credential",
    "Insecure Configuration": "insecure_config",
    "Weak Cryptography": "weak_crypto",
    "Race Condition": "race_condition",
}
# Types matched by (file, name) rather than (file, line).
NAME_TYPES = {"dead_import", "dead_function", "high_complexity"}
LINE_TOL = 2


def _norm(p):
    return str(p).replace("\\", "/")


def _name_of(x):
    if isinstance(x, dict):
        return x.get("name") or x.get("import") or x.get("function") or ""
    return str(x)


class Finding:
    __slots__ = ("type", "file", "line", "name")

    def __init__(self, type, file, line=0, name=None):
        self.type = type
        self.file = _norm(file)
        self.line = int(line or 0)
        self.name = name

    def __repr__(self):
        loc = self.name if self.name is not None else f"L{self.line}"
        return f"{self.type:22} {self.file}:{loc}"


# ----------------------------------------------------------
# Extraction: run the deterministic engines, normalise to Findings.
# ----------------------------------------------------------

def extract_findings(repo_path):
    files = analyze_repository(str(repo_path))
    out = []
    sources = {}
    for f in files:
        if not f.get("is_code", False):
            continue
        path = _norm(f["file_path"])
        code = f.get("content", "")
        sources[path] = code

        for iss in detect_security_issues(code, is_test_file=f.get("is_test", False),
                                          file_path=path):
            t = SEC_TYPE_MAP.get(iss.get("type"))
            if t:
                out.append(Finding(t, path, line=iss.get("line", 0)))

        dc = f.get("dead_code", {}) or {}
        for imp in dc.get("unused_imports", []) or []:
            out.append(Finding("dead_import", path, name=_name_of(imp)))
        for fn in dc.get("unused_functions", []) or []:
            out.append(Finding("dead_function", path, name=_name_of(fn)))

        for m in f.get("complexity_metrics", []) or []:
            if m.get("risk_level") in ("warning", "error"):
                out.append(Finding("high_complexity", path, name=m.get("function")))

    try:
        for tf in propagate_interprocedural_taint(sources):
            out.append(Finding("taint_sink", _norm(getattr(tf, "file", "")),
                               line=getattr(tf, "line", 0)))
    except Exception as e:  # taint is best-effort; never crash the benchmark
        print(f"[warn] interprocedural taint pass failed: {e!r}")
    return out


def _matches(fnd, label):
    if fnd.type != label["type"]:
        return False
    if _norm(fnd.file) != _norm(label["file"]):
        return False
    if fnd.type in NAME_TYPES:
        return fnd.name == label.get("name")
    return abs(fnd.line - int(label.get("line", 0))) <= LINE_TOL


# ----------------------------------------------------------
# Scoring
# ----------------------------------------------------------

def _blank():
    return {"tp": 0, "fn": 0, "fp": 0}


def score_fixture(findings, labels):
    """Exact ground truth. Scope scoring to the types this fixture declares
    (via expected+decoys) so an incidental unrelated finding is not counted."""
    expected = labels.get("expected", [])
    decoys = labels.get("decoys", [])
    declared = {l["type"] for l in expected} | {d["type"] for d in decoys}
    stats = defaultdict(_blank)
    for l in expected:
        hit = any(_matches(f, l) for f in findings)
        stats[l["type"]]["tp" if hit else "fn"] += 1
    for f in findings:
        if f.type not in declared:
            continue
        if not any(_matches(f, l) for l in expected):
            stats[f.type]["fp"] += 1  # spurious (incl. any decoy that got flagged)
    return stats


def score_real(findings, labels):
    """Spot-labelled subset only. Each label carries flag=True (should be
    flagged) or flag=False (decoy). Findings outside the labelled set are
    ignored — real repos are not exhaustively labelled."""
    stats = defaultdict(_blank)
    for l in labels:
        hit = any(_matches(f, l) for f in findings)
        if l.get("flag", True):
            stats[l["type"]]["tp" if hit else "fn"] += 1
        elif hit:
            stats[l["type"]]["fp"] += 1
    return stats


def _pr(c):
    tp, fp, fn = c["tp"], c["fp"], c["fn"]
    prec = tp / (tp + fp) if (tp + fp) else 1.0
    rec = tp / (tp + fn) if (tp + fn) else 1.0
    return prec, rec


def _merge(into, other):
    for t, c in other.items():
        for k in ("tp", "fn", "fp"):
            into[t][k] += c[k]


def _print_table(title, agg):
    print(f"\n{title}")
    print("-" * 74)
    print(f"{'finding_type':24} {'prec':>6} {'recall':>7} {'TP':>4} {'FP':>4} {'FN':>4}")
    print("-" * 74)
    for t in sorted(agg):
        c = agg[t]
        prec, rec = _pr(c)
        print(f"{t:24} {prec:6.2f} {rec:7.2f} {c['tp']:4d} {c['fp']:4d} {c['fn']:4d}")


# ----------------------------------------------------------
# Real-repo cloning (pinned)
# ----------------------------------------------------------

def _ensure_clone(entry):
    CLONE_CACHE.mkdir(parents=True, exist_ok=True)
    dest = CLONE_CACHE / entry["name"]
    sha = entry["commit"]
    if not (dest / ".git").is_dir():
        subprocess.run(["git", "clone", "--quiet", "--branch", entry["tag"],
                        "--depth", "1", entry["url"], str(dest)], check=True, timeout=300)
    head = subprocess.run(["git", "-C", str(dest), "rev-parse", "HEAD"],
                          check=True, capture_output=True, text=True).stdout.strip()
    if head != sha:
        print(f"[warn] {entry['name']} HEAD {head[:12]} != pinned {sha[:12]} "
              f"(tag may have moved); results are for HEAD")
    return dest, head


# ----------------------------------------------------------
# Main
# ----------------------------------------------------------

def load_json(p):
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def _fixture_names():
    # Skip dot-directories (e.g. a stray .impeccable dropped by another tool).
    return sorted(p.name for p in FIXTURES.iterdir()
                  if p.is_dir() and not p.name.startswith("."))


def run_fixtures(dump=False):
    # Fixtures are discovered from the filesystem so --dump works before
    # labels.json exists (labels are authored FROM the dump).
    labels_all = {} if dump else load_json(CORPUS / "labels.json")
    agg = defaultdict(_blank)
    for name in _fixture_names():
        repo = FIXTURES / name
        findings = extract_findings(repo)
        if dump:
            print(f"\n### fixture {name} — {len(findings)} findings")
            for f in sorted(findings, key=lambda x: (x.type, x.file, x.line, x.name or "")):
                print("   ", f)
            continue
        _merge(agg, score_fixture(findings, labels_all.get(name, {"expected": [], "decoys": []})))
    return agg


def run_real(dump=False):
    entries = load_json(CORPUS / "real_repos.json")
    agg = defaultdict(_blank)
    for entry in entries:
        try:
            dest, head = _ensure_clone(entry)
        except Exception as e:
            print(f"[warn] could not clone {entry['name']}: {e!r} — skipping")
            continue
        findings = extract_findings(dest)
        if dump:
            print(f"\n### real {entry['name']} @ {head[:12]} — {len(findings)} findings")
            for f in sorted(findings, key=lambda x: (x.type, x.file, x.line, x.name or "")):
                print("   ", f)
            continue
        _merge(agg, score_real(findings, entry.get("labels", [])))
    return agg


def main():
    ap = argparse.ArgumentParser(description="ET Code Analyzer benchmark corpus")
    ap.add_argument("--gate", action="store_true",
                    help="exit non-zero if fixture P/R regresses below thresholds.json")
    ap.add_argument("--no-real", action="store_true", help="skip pinned real-repo clones")
    ap.add_argument("--dump", action="store_true", help="print raw findings and exit")
    args = ap.parse_args()

    if args.dump:
        run_fixtures(dump=True)
        if not args.no_real:
            run_real(dump=True)
        return 0

    print("=" * 74)
    print("ET Code Analyzer — benchmark corpus (deterministic engines only)")
    print("=" * 74)

    fx = run_fixtures()
    _print_table("FIXTURES (curated ground truth) — THIS IS THE RELEASE GATE", fx)

    exit_code = 0
    if args.gate:
        thresholds = load_json(CORPUS / "thresholds.json")
        print("\nGATE CHECK vs corpus/thresholds.json")
        print("-" * 74)
        failures = []
        for t, c in sorted(fx.items()):
            prec, rec = _pr(c)
            th = thresholds.get(t, {"precision": 0.0, "recall": 0.0})
            ok = prec >= th["precision"] - 1e-9 and rec >= th["recall"] - 1e-9
            flag = "OK " if ok else "FAIL"
            print(f"  [{flag}] {t:24} prec {prec:.2f}>={th['precision']:.2f}  "
                  f"recall {rec:.2f}>={th['recall']:.2f}")
            if not ok:
                failures.append(t)
        if failures:
            exit_code = 1
            print(f"\nGATE FAILED: {len(failures)} finding type(s) regressed: {failures}")
        else:
            print("\nGATE PASSED: no per-type precision/recall regression.")

    if not args.no_real:
        real = run_real()
        # Prominent, clearly-separated section: this is the portfolio-facing number.
        print("\n" + "#" * 74)
        print("# REAL-REPO REALITY CHECK (report-only, NOT gating)")
        print("#   flask 3.0.3 = clean anchor · bottle 0.13.2 = organic-mess anchor")
        print("#" * 74)
        _print_table("REAL REPOS (pinned, spot-labelled) — precision/recall", real)
        overall = _blank()
        for c in real.values():
            for k in overall:
                overall[k] += c[k]
        prec, rec = _pr(overall)
        print(f"\n  >>> REAL-REPO OVERALL: precision {prec:.2f}  recall {rec:.2f}  "
              f"(TP {overall['tp']}, FP {overall['fp']}, FN {overall['fn']})")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
