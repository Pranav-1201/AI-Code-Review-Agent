# Analyzer accuracy review — 3 repos, independent cross-check

**Date:** 2026-08-19
**Question asked:** is the output good enough to deploy publicly?
**Short answer:** not yet. Two false-positive classes fire on ordinary,
non-security code and they are loud — High severity, 0.8 confidence. On Flask,
**every single security finding the tool produced was wrong.**

## Method

Three repos cloned at pinned SHAs and analysed independently. The independent
pass deliberately used established third-party tools rather than a
reimplementation of the analyzer, because a hand-rolled checker would share the
blind spots being measured.

| Repo | SHA | Tracked `.py` | Python LOC |
|---|---|---|---|
| `Pranav-1201/AI-Code-Review-Agent` | `00a11a64` | 102 | 18,336 |
| `pallets/flask` | `d318b683` | 83 | 18,345 |
| `diya-garg18/RL-Project` | `54e0b4e8` | 46 | 8,534 |

Independent tooling: `bandit 1.9.4`, `radon 6.0.1`, `pyflakes 3.4.0`,
`vulture 2.16`, installed into a throwaway venv so the project venv was not
disturbed.

Note on independence: the report schema was extracted first (key names and
types only, no values) so the independent pass was not anchored on the tool's
answers. Enum vocabularies were read from the analyzer source, not the reports.

---

## Verdict per repo

| | AI-Code-Review-Agent | flask | RL-Project |
|---|---|---|---|
| Security findings reported | 28 | 5 | 4 |
| Confirmed false positives | at least 5 | **5 of 5** | **2 of 4** |
| Security precision | not fully triaged | **0.00** | **0.50** |

---

## TIER 1 — defects that block public deployment

### 1. Any `.run()` call is reported as Command Injection

The detector matches the bare method name `run`, with no check that the callee
is `subprocess`. Verified against source:

| Location | Actual code | Reported as |
|---|---|---|
| `flask tests/test_basic.py:1642` | `app.run(debug=debug, ...)` — Flask's own dev server | Command Injection, Low, conf 0.8 |
| `flask tests/test_basic.py:1902` | `app.run(hostname, port, debug=True)` | Command Injection, Medium, conf 0.6 |
| `flask tests/test_basic.py:1928` | `app.run(host, port)` | Command Injection, Medium, conf 0.55 |
| `flask tests/test_templating.py:481` | `app.run()` | Command Injection, Low, conf 0.8 |
| `flask examples/celery/src/task_app/__init__.py:33` | `self.run(*args, **kwargs)` — a **Celery task method** | Command Injection, Medium, conf 0.55 |

`bandit` found **zero** command-injection issues in Flask. All five are wrong.

This is the single most damaging defect: `.run()` is one of the most common
method names in Python. Every Flask, Celery, unittest, and subprocess-free
codebase will trip it.

**Fix:** resolve the call target before flagging. Require the callee to be
`subprocess.<fn>` / `os.system` / `os.popen`, either by tracking the import
binding or by checking the attribute chain root.

### 2. English prose in an f-string is reported as SQL Injection (High, conf 0.8)

`visit_JoinedStr` in `backend/app/services/security_analyzer.py` scans every
f-string for the **substrings** `select`, `insert`, `update`, `delete`, with no
check for SQL syntax and no check that the value reaches a database call.

Verified against source in RL-Project — a reinforcement-learning repo with no
database and no SQL anywhere:

- `scripts/aggregate_dqn.py:60` → flagged **SQL Injection, High, conf 0.8**.
  The matching text is a `raise SystemExit` message:
  `"Delete the odd ones out or re-run them."` — the word **"Delete"**.
- `tests/test_no_ground_truth_leakage.py:69` → flagged **SQL Injection, High,
  conf 0.8**. The matching text is an assert message:
  `"then update this whitelist AND EXPLAIN.md."` — the word **"update"**.

Both are pure English. Neither has any SQL. Both are reported at the highest
severity the tool emits, with 0.8 confidence, and both reached
`insights.top_critical_issues`.

The same weakness exists in `visit_BinOp` for string concatenation.

**Fix:** require SQL *shape*, not a keyword — e.g. a leading verb plus a
`FROM`/`INTO`/`SET`/`WHERE` clause — and, better, only flag when the string
flows into a cursor/execute sink. The taint analyzer already models that sink;
this detector is not using it.

### 3. `subprocess` with a list and no shell is still flagged

`RL-Project scripts/commit_balance.py:40`:

```python
return subprocess.run(
    ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
).stdout.strip()
```

List argv, `shell=False` — not a shell-injection vector. Reported Medium,
conf 0.55. Same for `scripts/run_dqn_sweep.py:237`, a `subprocess.Popen(cmd)`
where `cmd` is a list.

This is the defect Phase C recorded as fixed (`command_injection` precision
0.66 → 1.00). The fixture gate passes, but the fix does **not** generalise:
the benchmark fixture uses a literal list, while real code uses
`[*unpacking]` and list variables. **The gate at 1.00 is currently ratifying a
narrower fix than it appears to.**

**Fix:** treat any `subprocess.*` call whose first arg is a list/tuple (or a
name bound to one) with `shell` not True as safe. Add a corpus fixture with
`["git", *args]` so the gate covers the real pattern.

---

## TIER 2 — accuracy and completeness gaps

### 4. Dependency versions and CVE lookup are largely inert

- **Zero vulnerabilities reported across all three repos**, for every
  dependency. That includes Flask's pinned `jinja2==3.1.2` and
  `markupsafe==2.1.1`, both years old. `analysis-boundaries` documents that
  OSV network failures are **silent** — so an empty result is
  indistinguishable from a failed lookup. That ambiguity is not acceptable in
  a published report.
  **Fix:** record lookup status per dependency (`checked` / `unreachable`) and
  surface "could not check" in the UI instead of an implied clean bill.
- **`version: "unknown"`** on 8 of 21 dependencies for AI-Code-Review-Agent
  (numpy, scikit-learn, pandas, fastapi, uvicorn, pydantic, python-multipart,
  GitPython) — these are unpinned in `requirements.txt`, but
  `requirements.lock` **is present and holds exact versions** and is not read.
  Flask ships `uv.lock`, also unread.
- **`flit_core==3.11,<4`** — a version *constraint* stored in the `version`
  field. The parser split on the wrong delimiter.
- **`latestVersion: "unknown"`** on 3 of 8 Flask deps, so `isOutdated: false`
  there means "unknown", not "current".

### 5. Complexity numbers disagree with radon, in both directions

| File | Report `maxCyclomaticComplexity` | radon max block | Δ |
|---|---|---|---|
| `backend/app/services/repository_review_engine.py` | 34 | **58** (`review_repository`) | −24 |
| `flask src/flask/cli.py` | 13 | **18** (`routes_command`) | −5 |
| `backend/app/analysis/taint_analyzer.py` | 41 | 32 | +9 |
| `backend/app/analysis/call_graph.py` | 37 | 30 | +7 |
| `backend/app/analysis/dependency_analyzer.py` | 61 | 59 | +2 |

Some divergence is expected (different counting conventions), but −24 on
`repository_review_engine.py` is too large to be convention. Worth a direct
comparison on one function.

Separately: **test files are excluded from the complexity ranking** while being
counted in `files` and `test_files`. Flask's most complex block in the whole
repo is `tests/test_basic.py:1144 test_response_types` at CC 27 — higher than
anything in `src/flask/` — and it appears nowhere in `most_complex_files`.
Either is defensible; it should be stated in the report.

### 6. Scanning this repo reports its own benchmark fixtures as findings

5 of the 28 findings for AI-Code-Review-Agent come from
`backend/benchmark/corpus/fixtures/`, files that are *deliberately vulnerable*
by design, including two that reached `top_critical_issues`. Any repo
containing security test fixtures gets the same noise.

**Fix:** treat a path under a benchmark/fixture corpus like a test file, or let
repos declare an ignore path.

### 7. Reporting and presentation

- **`summary.security_issues` counts production files only** — verified: 26/28,
  1/5, 3/4 all match the production-only subtotal exactly. This is consistent
  and intentional, **not a bug**, but a reader seeing "1 security issue" beside
  a file list containing 5 will read it as a defect. Rename it
  `security_issues_production` or show both.
- **`languages: [... ('JavaScript', 0)]`** for AI-Code-Review-Agent, which has
  3 JavaScript files. Rounded to 0% and rendered as a zero-width slice.
- **`healthScore` 54 vs `avg_score` 90.3** on the same repo. Two headline
  numbers 36 points apart with no stated relationship invites the reader to
  distrust both.
- **`most_reused_module: "flask"`** when analysing Flask, and
  `most_reused_module: "os"` for AI-Code-Review-Agent. Technically true,
  analytically empty. Exclude stdlib and the repo's own package name.
- **`duplicates: 0`** for AI-Code-Review-Agent, while Flask reports one pair at
  `similarity: 35`. A 35% similarity threshold is low enough that reporting it
  as a "duplicate" overstates the finding.

### 8. Dead code is not reported at all

None of the three reports contain a `dead_import` or `dead_function` finding,
though `thresholds.json` carries both at precision/recall 1.00. Independent
pass found real ones:

- AI-Code-Review-Agent: **12** unused imports (pyflakes), incl.
  `heuristic_refactor_engine.py:28 're'`, `llm_service.py:9 'ast'`,
  `llm_service.py:57 'torch'`, plus 3 assigned-but-unused locals
  (`repository_review_engine.py:392 total_score`, `:637 cc`,
  `report_generator.py:218 review_id`)
- flask: **45** unused imports (most are legitimate `__init__.py` re-exports)
- RL-Project: **3** unused imports

If the detector runs but its output is not carried into the report JSON, that
is a wiring bug worth finding before launch.

---

## What is working well

Stated plainly, because the list above is one-sided:

- **Unsafe deserialization matched exactly** — 4 reported vs 4 from bandit on
  AI-Code-Review-Agent, including the real `pickle.load` in
  `retriever_service.py:85`, correctly rated Critical. The Phase C fix holds.
- **The eval/exec/SHA-1 suppressions on Flask are correct, not misses.**
  `cli.py:1023` (PYTHONSTARTUP), `config.py:209` (`from_pyfile`), and
  `sessions.py:281` (SHA-1 under HMAC for session signing) are all flagged by
  bandit and all correctly suppressed here. That is the documented design
  working as intended, and bandit is the less precise tool on these three.
- File classification (production vs test) matched the repo layout in all three.
- `RL-Project` file coverage was exact: 46 of 46.
- Missing files in the other two are **empty `__init__.py`** only (7 and 3) —
  correct behaviour, not a coverage gap.
- The explanation layer was `deterministic` throughout — no LLM invention.

---

## Recommendation

**Do not deploy publicly until Tier 1 items 1 and 2 are fixed.** They are not
edge cases: `.run()` and the word "update" in an error string are everywhere in
normal Python. A reviewer who runs this on their own repo will see High-severity
security findings that are plainly wrong, and that is the impression that
sticks.

Suggested order:

1. Fix `.run()` callee resolution (item 1) — largest precision win
2. Fix f-string SQL heuristic (item 2) — highest severity of the wrong findings
3. Add real-world fixtures for both to the benchmark corpus, so the gate stops
   reporting 1.00 for detectors that fail on real code
4. Make the OSV lookup report its own failure (item 4)
5. Then re-run this comparison

Items 5–8 are quality work that can follow a first public release.
