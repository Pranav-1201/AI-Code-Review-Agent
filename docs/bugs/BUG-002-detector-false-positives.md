# BUG-002 — three detectors report false positives on ordinary code

**Status:** **CLOSED 2026-09-05** — all three defects fixed in Phase G and
re-measured against the shipped detector this session.
**Severity:** was P0 — blocks public deployment
**Found:** 2026-08-19 by measurement, not by report
**Investigated by:** Claude Opus 5, session `a55eaf1f`
**Fix owner:** Phase G — shipped in session `0f899c51`
**Closed by:** Claude Opus 5, session `81d7c85b`

---

## Closure evidence (2026-09-05, run fresh)

This file sat at "OPEN, P0, blocks public deployment" for weeks after the work
that fixed it had shipped, which is a worse failure than the bug: anyone
reading `docs/bugs/` to judge deploy-readiness was told the blocker was live.

Every snippet in the evidence tables below was replayed through
`detect_security_issues` as it ships today:

| Defect | Cases | Result |
|---|---|---|
| A (S1) — `.run()` is Command Injection | all 5 Flask/Celery findings | **0 findings each** |
| B (S2) — prose f-string is SQL Injection | 2 | **0 findings each** |
| C (S3) — safe list argv | 1 (`["git", *args]`) | **0 findings** |
| **Control** — real injections must still fire | 2 (`["sh","-c",user]`, `os.system("ls "+user)`) | **1 Command Injection each** |

The control row is the half that matters: a detector fixed by being switched
off would pass the first three rows too.

**What is NOT closed by this.** Detector precision overall is still not 1.00.
The report-only real-repo check in `run_benchmark.py --gate` measured, this
session, **precision 0.60 / recall 1.00 (TP 6, FP 4, FN 0)** — the 4 false
positives being `dangerous_function` (3) and `weak_crypto` (1). Those are
different detectors from A/B/C and were never what this bug described. They
have no bug file of their own; if they are ever worked, open one.

---

## How it was found

Three repositories were cloned at pinned commits and analysed twice — once by
this tool, once by established third-party analysers (`bandit 1.9.4`,
`radon 6.0.1`, `pyflakes 3.4.0`, `vulture 2.16`) installed into a throwaway
venv. Every disagreement was then triaged against source.

Full study: `docs/ANALYZER_ACCURACY_2026-08.md`.

| Repository | Commit | Reported | Confirmed false | Precision |
|---|---|---|---|---|
| `pallets/flask` | `d318b683` | 5 | **5** | **0.00** |
| `diya-garg18/RL-Project` | `54e0b4e8` | 4 | 2 | 0.50 |
| this repo | `00a11a64` | 28 | ≥5 | not fully triaged |

---

## Defect A (S1) — any `.run()` is Command Injection

**Root cause:** the detector matches the bare method name `run` with no check
that the callee resolves to `subprocess`.

**Evidence — all five Flask findings are this one mistake:**

| Location | Actual code | Reported as |
|---|---|---|
| `tests/test_basic.py:1642` | `app.run(debug=..., use_debugger=...)` | Command Injection, Low, 0.8 |
| `tests/test_basic.py:1902` | `app.run(hostname, port, debug=True)` | Command Injection, Medium, 0.6 |
| `tests/test_basic.py:1928` | `app.run(host, port)` | Command Injection, Medium, 0.55 |
| `tests/test_templating.py:481` | `app.run()` | Command Injection, Low, 0.8 |
| `examples/celery/src/task_app/__init__.py:33` | `self.run(*args, **kwargs)` — a Celery task | Command Injection, Medium, 0.55 |

`bandit` found **zero** command-injection issues in Flask.

**Fix:** resolve the call target before flagging. Require the callee to be
`subprocess.<fn>`, `os.system` or `os.popen`, either by tracking the import
binding or by walking the attribute chain to its root.

**Why it is the worst of the three:** `.run()` is one of the most common method
names in Python. Flask, Celery, unittest and countless others trip it.

---

## Defect B (S2) — English prose in an f-string is SQL Injection

**Root cause:** `visit_JoinedStr` in
`backend/app/services/security_analyzer.py` scans every f-string for the
substrings `select`, `insert`, `update`, `delete`, case-insensitively. No check
for SQL syntax. No check that the value reaches a database call.

**Evidence — an RL repo with no database and no SQL anywhere:**

`scripts/aggregate_dqn.py:60` → **SQL Injection, High, confidence 0.8**
```python
raise SystemExit(
    f"runs in {directory} disagree on '{field}': {sorted(values)}\n"
    f"These are not the same experiment and must not be averaged. "
    f"Delete the odd ones out or re-run them."
)
```
The match is the word **"Delete"** in an error message.

`tests/test_no_ground_truth_leakage.py:69` → **SQL Injection, High, 0.8**
```python
assert actual == allowed, (
    f"EnvSnapshot fields changed: {actual ^ allowed}. If deliberate, prove the new "
    "field encodes no ground truth, then update this whitelist AND EXPLAIN.md."
)
```
The match is **"update"**. (Note the second fragment is a plain string — implicit
concatenation with an f-string still produces one `JoinedStr` node.)

Both were emitted at the highest severity the tool produces, and both reached
`insights.top_critical_issues`.

**The same weakness exists in `visit_BinOp`** for string concatenation.

**Fix:** require SQL *shape* — a leading verb plus a `FROM`/`INTO`/`SET`/`WHERE`
clause — and, better, only flag when the string flows into a cursor/execute
sink. The taint analyzer already models that sink; this detector is not using
it.

---

## Defect C (S3) — the benchmark gate is narrower than it reads

**Root cause:** the Phase C fix for `command_injection` (precision 0.66 → 1.00)
handles the corpus fixture's *literal* list, but not the shapes real code uses.

**Evidence:**
```python
# RL-Project scripts/commit_balance.py:40 → reported Medium
return subprocess.run(
    ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
).stdout.strip()

# RL-Project scripts/run_dqn_sweep.py:237 → reported Medium
proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, cwd=str(ROOT))
```
List argv, no shell. Neither is a shell-injection vector.

**Why this one is dangerous beyond its own severity:** every floor in
`backend/benchmark/corpus/thresholds.json` reads 1.00, so the gate reports
perfect precision while the real-world pattern fails. **A green gate is not
evidence of a correct detector.**

**Fix:** treat any `subprocess.*` call whose first argument is a list or tuple —
including `[*unpacking]` and names bound to lists — with `shell` not True as
safe. Add a fixture using `["git", *args]` so the gate covers the real pattern.

---

## Two candidates checked and dismissed

Recorded so nobody re-files them.

**`summary.security_issues` is not an undercount.** It disagreed with the
findings count in all three reports (26 vs 28, 1 vs 5, 3 vs 4), which looked
like a bug. Recomputing showed it is a **production-only** count — matching
26/26, 1/1 and 3/3 exactly. Consistent and intentional. It should be *renamed*
for clarity (idea F15), not fixed.

**Flask's `eval`, `exec` and SHA-1 are correctly suppressed.**
`cli.py:1023` (PYTHONSTARTUP), `config.py:209` (`from_pyfile`) and
`sessions.py:281` (SHA-1 under HMAC for session signing) are all flagged by
`bandit` and all correctly suppressed here. This is the documented
benign-pattern design working as intended — on these three, this tool is the
more precise instrument.

---

## Verification once fixed

1. Write the fixtures **first**, and confirm they fail before any fix. A test
   written after the fix proves only that it matches the code.
2. `venv/Scripts/python.exe -m pytest backend/tests -q` → ≥329 passed
3. `venv/Scripts/python.exe backend/benchmark/run_benchmark.py` → no type below
   its floor
4. Re-scan `pallets/flask` at `d318b683` → **0 security findings**
5. Re-scan the RL project at `54e0b4e8` → **0 SQL Injection findings**
6. Re-scan this repo → the count should drop from 28, and no finding should come
   from `backend/benchmark/corpus/fixtures/` (that is idea S9, separate)
7. Raise the thresholds to match the new behaviour

---

## Related

- `docs/ANALYZER_ACCURACY_2026-08.md` — the full study with method
- `docs/STAFF_AUDIT_2026-08-19.md` — Phase G, ideas S1–S4
- `docs/DECISIONS.md` D9 (false-negative preference), D10 (floor policy),
  D12 (repositioning)
