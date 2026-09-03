# Phase L — dead-code wiring, corpus exclusion, hygiene

**Date:** 2026-09-04 · **Model:** Claude Opus 5 · **Branch base:** `main` @ `ac8e2db`

Phase L in `docs/STAFF_AUDIT_2026-08-19.md` lists eight IDs: S8, S9, F11, F12,
F13, F14, H1, H2. **This spec covers S8, S9, F12, F13 and H1.** F11 and F14 are
deferred to a follow-up session, with F11's approach already decided (see
"Deferred", below).

---

## 1. Ground truth measured before this design

Every number here was produced this session by running the shipped analyzer
against this repository, not read from a prior note.

| Fact | Value |
|---|---|
| Files analysed | 230 (185 production, 45 test) |
| Dead **imports** found by the analyze layer | **30** total, 2 of them inside fixtures |
| Dead **functions** found by the analyze layer | **462** total across 75 files |
| Dead/unused records reaching the report JSON | **0** |
| Typed records in the report | 55 `security`, 38 `maintainability`, 29 `performance`, 27 `complex_function`, 9 `style` |
| Report records sourced from `backend/benchmark/corpus/fixtures/` | **35** (33 `security` + 2 `complex_function`) |
| `Visualizations` bundle chunk | 432.04 kB (target < 250 kB) |

Composition of the 462 dead functions — the number that drives the whole design:

| Location | Count |
|---|---|
| `backend/tests` | 374 (372 of them named `test_*`) |
| `backend/validation` | 53 |
| `backend/benchmark` | 25 |
| `backend/app` | 7 |
| `backend/database` | 2 |
| `rag/data` | 1 |

Only **10** are production code, and at least one of those 10 is a false
positive: `backend/app/observability.py::format` is
`JsonFormatter(logging.Formatter).format`, invoked by the standard library and
never by name in this repo.

**The conclusion that shaped the design:** S8 is a *wiring* defect, not a
detector defect — the detector works and its output is discarded. But wiring it
naively would put roughly 452 known-noise findings into the report, which is
exactly the false-positive generator `CONSTRAINTS.md` §21 forbids. S9 is
therefore a prerequisite for S8 being safe, not merely hygiene alongside it.

---

## 2. S9 — exclude corpora, label the rest

### The existing contract

`repo_analyzer.classify_file_type()` returns a **fine** role from
`{test, cli_parser, data_model, utility, orchestrator}`. `coarse_file_type()`
maps fine → **coarse** `{production, test, non_code}` via
`_NON_PRODUCTION_ROLES = {"test", "non_code"}`. The scoring layer and the
frontend understand only the coarse value. This two-field split is documented in
the source and exists because a prior defect stored the fine role in `file_type`
and collapsed the health score.

Fixture files currently classify as fine `utility` → coarse `production`, so
they enter `prod_results` and their findings reach the report.

### The change

Add a **sixth fine role, `fixture`**, assigned by path in `classify_file_type`
when the normalised path contains any of:

```
/benchmark/corpus/    /fixtures/    /corpus/    /testdata/
```

The rule is deliberately generic rather than hardcoded to this repository: a
scanned third-party repo's own fixture corpus is not production code either.

`fixture` is added to `_NON_PRODUCTION_ROLES`, and `coarse_file_type` maps it to
**`test`** — *not* to a new coarse value. This preserves the documented
three-value coarse contract exactly, so `prod_results`, the health score, the
`production_files` / `non_production_files` counts and the frontend all require
no change. Fixtures simply stop counting as production.

### Two behaviours, keyed on different fields

- **Exclude (fine role).** A file whose *fine* role is `fixture` emits **no
  findings at all** — no `issues`, no `security_risks`. These are our own
  deliberately-planted vulnerabilities; reporting them as real is simply wrong,
  and it is the specific defect S9 names.
- **Label (coarse type).** Every emitted finding gains a `file_type` field
  carrying the coarse value, so findings in test files stay visible and
  filterable rather than being silently dropped.

The file still appears in `file_reports` with its real line count and language,
so file totals stay honest. Only its findings are suppressed.

---

## 3. S8 — wire dead-code findings into the report

### 3.1 Where the findings are emitted

In `repository_review_engine.analyze_single_file`, alongside the existing
`formatted_issues` construction. That function already receives everything
needed: `code = file_data["content"]`, `file_role`, and the `dead_code` dict,
which by that point is fully populated — `RepoAnalyzer.analyze_repository`
runs the cross-file dead-function reduce *before* `review_repository` is called.

`formatted_issues` is the list that feeds the per-file `issues` array, the Issue
Explorer and the severity tiers, so this is the list the audit means by "reach
report JSON".

### 3.2 Scope

| Finding type | Emitted for |
|---|---|
| `dead_import` | all non-fixture files |
| `dead_function` | **production files only** (coarse `file_type == "production"`) |

Restricting `dead_function` to production removes the 374 `backend/tests`
findings without touching the detector. `backend/validation` stays production by
decision (§6), so its ~53 findings will appear and are expected.

### 3.3 The explanation contract

J1 and J2 established that every finding carries `why_it_matters`, `how_to_fix`,
`snippet` and `confidence`, and J2's acceptance bar was "31 findings, 31 with
real source, 0 placeholders". Dead-code findings must meet the same bar.

| Field | `dead_import` | `dead_function` |
|---|---|---|
| `severity` | `low` | `low` |
| `confidence` | 0.9 — alias-aware, single source of truth in `call_graph` | 0.7 — interprocedural but deliberately conservative |
| `snippet` | the import statement line | the `def` line |
| `line` | resolved (§3.4) | resolved (§3.4) |

### 3.4 Resolving line numbers and snippets

The detector returns bare names, not locations. Three options were considered:

- **Chosen — resolve at the report layer.** `analyze_single_file` already holds
  `content`. A small helper walks the AST once and maps each reported name to
  its line number and source line. **No detector contract change, so nothing
  downstream breaks.**
- **Rejected — widen the detector to return `{name, lineno}` dicts.** The
  benchmark already tolerates this shape (`run_benchmark._name_of` handles
  dict-or-string), but it breaks six assertions across
  `backend/tests/test_dead_code.py` and `backend/validation/phase4_validation.py`
  for no benefit the chosen option does not already deliver.
- **Rejected — emit with `line: 0` and an empty snippet.** Cheapest, and it
  regresses the placeholder-free property J2 was built to establish.

### 3.5 The false-positive guard

`call_graph.find_dead_functions` already exempts functions that are decorated
entrypoints, dunders, members of a dynamic-dispatch class, top-level `main`, or
referenced by name as a value. Two real exemptions are missing, both measured
this session:

1. **pytest's naming convention.** pytest collects `test_*` by name, with no
   decorator. 372 findings.
2. **Overrides of an external base class.** `JsonFormatter(logging.Formatter)`
   defines `format`, called by the standard library. The class's bases are
   already parsed (the dynamic-dispatch check reads them), so a method whose
   class has a base **not defined anywhere in the repository** should be treated
   as an entrypoint.

**These are fixed in `call_graph.py`, not filtered at the report layer.**
Filtering downstream would leave the benchmark measuring an analyzer that still
calls `Formatter.format` dead — a gate ratifying a known defect, which is the
failure mode `CONSTRAINTS.md` §11 exists to prevent.

**Gate safety, checked before designing this:** the `f6_dead_functions` fixture's
two true positives are `_never_called` (in `main.py`) and `orphan` (in
`helpers.py`). Neither is named `test_*` and neither is a method of any class, so
neither guard can suppress them. Recall stays 1.00.

### 3.6 Cache invalidation

`analyze_single_file` caches on `version="v3.6"`, and its version history shows
every prior behaviour change bumped it. Adding findings changes issue output, so
the version **must** move to `v3.7`. Without the bump a warm cache would serve
pre-change results and the acceptance run would measure nothing.

---

## 4. Hygiene tail

| ID | Change |
|---|---|
| **F12** | Delete `frontend/src/pages/Index.tsx` — a dead placeholder, not referenced by `routes.ts`. |
| **F13** | `frontend/src/lib/response-mapper.ts:79` uses `Math.round((lines / totalLines) * 100)`, so any language under 0.5% renders as `0%`. Render `<1%` for a non-zero share that rounds to zero. |
| **H1** | `390.52` is a tracked zero-byte file. `git rm --cached` it and delete it. Add `.gitignore` entries for the **specific** junk names `HANDOVER.md` §4 records (`390.52`, `1.0`, `bool`, `str`, `dict`, `exact`, `analyzer`) — deliberately *not* a wildcard for extensionless files, which would hide real ones such as `Caddyfile`. A backtick-named zero-byte file appeared again during this session and was deleted. |
| **H2** | Already satisfied — the working tree was clean at session start. |

---

## 5. Testing

Test-driven per item, one logical change per commit, explicit paths staged.

**Every new fixture must be observed failing against pre-fix code before the fix
lands.** This is the audit's own rule and the reason it is worth restating: the
release gate once read precision 1.00 across all eleven types while every single
security finding on flask was a false positive, because the fixtures passed both
before and after.

### Acceptance criteria

| Criterion | Expected |
|---|---|
| Rescan this repo → `dead_import` findings in the report | **≥ 12** (30 measured at the analyze layer, 28 outside fixtures) |
| Rescan this repo → findings sourced from `benchmark/corpus/fixtures/` | **0** (35 today) |
| `backend/app/observability.py::format` reported dead | **no** |
| Benchmark fixture gate | `GATE PASSED`, no per-type precision or recall below its recorded baseline |
| `venv/Scripts/python.exe -m pytest backend/tests -q` | passes, count ≥ 444 |
| `npm run typecheck` (`tsc -b`, **not** `tsc --noEmit`) | exit 0 |
| `npx vitest run` | passes |
| `npm run build` | succeeds |

The suite is not the acceptance criterion. Per `HANDOVER.md` §3, the bar for
anything shipping is a **real clone driven through the real UI** — two of the
previous session's three findings were invisible to a fully green 440-test suite
and surfaced only when the app was actually driven.

---

## 6. Decisions taken during design

| Decision | Choice | Reasoning |
|---|---|---|
| How far to wire S8 | dead imports everywhere + dead functions in production files only, with an FP guard | 452 of 462 dead-function findings are noise; wiring them all would violate `CONSTRAINTS.md` §21 |
| Non-production findings | exclude corpora entirely, label everything else | fixtures are planted vulnerabilities and reporting them is wrong; test-file findings are debatable and better filtered in the UI than dropped |
| `backend/validation/` | **stays production** | it is not a corpus, S9 was scoped to corpora, and its ~53 dead functions are largely genuine — they are one-shot phase scripts with real orphaned helpers |
| Where the FP guard lives | `call_graph.py` | a report-layer filter would hide a known detector defect from the precision metric that is supposed to catch it |
| Coarse mapping for `fixture` | → `test` | preserves the documented three-value coarse contract; no frontend or scoring change |

---

## 7. Deferred

**F11 — split the 432 kB `Visualizations` chunk.** Approach already decided:
`React.lazy` the chart sections so the page shell renders immediately and
recharts streams in behind a skeleton.

Recorded because it changes how the audit's criterion should be read:
`Visualizations` is **already a lazy route chunk**, so its 432 kB downloads only
when that page is opened. A `manualChunks` rule moving recharts into a vendor
chunk would satisfy the audit's literal wording ("Visualizations chunk < 250 kB")
while making the application no faster at all. The criterion measures chunk size
where the thing worth improving is time-to-first-paint on that route.

**F14 — reconcile `health_score` with the average quality score.** Measured this
session: the backend reports `health_score: 53` and `average_quality_score: 90.56`
in the same `repository_summary`, and the frontend computes its own separate
score in `response-mapper.ts`. Two independent computations, both surfaced. Needs
either reconciliation or an explicit in-UI explanation of what each one means.
