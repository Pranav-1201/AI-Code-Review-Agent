# HANDOVER — read this first, every session

**Purpose:** this file is the entry point. If you have been told something as
short as *"finish my project"*, this file is the whole brief. Read it, then
`docs/CONSTRAINTS.md`, then start at the next unfinished phase below.

**Last updated:** 2026-08-20 · **Updated by:** Claude Opus 5 session
`cc9e8871` · **Branch at handover:** `phase-j/j1-explanation-parity`, **unpushed**,
5 commits ahead of `main` at `f1cedf7`.

> **Phase J is underway — J1 is mid-flight.** Everything on `main` is pushed
> (the earlier note claiming F2 was unpushed was stale; `git rev-list --count
> origin/main..main` returns 0). Resume from
> `.superpowers/sdd/2026-08-20-j1-explanation-parity/progress.md` — that ledger
> is the recovery map and names every commit. **Tasks 1-3 complete and
> review-clean; Task 4 implemented and fixed but its scoped re-review was never
> run — do not mark it complete until that happens.** Tasks 5-7 not started.
> Frontend suite is **56 passed / 10 files** (was 42/6 when J1 started).

---

## 1. Where things stand right now

The project is an AI code review agent: you give it a public repository URL, it
clones it, runs a deterministic AST analysis, and returns a health report.

**Status: strong MVP, Phases G and H done, F2 (the last open defect) fixed,
not yet deployed.** Graded
**6.5/10** in `docs/STAFF_AUDIT_2026-08-19.md`, before either. The engineering
around the product was already good (security 8, tests 8, docs 8); the
analyzer's precision was the failing grade (correctness 4), and G fixed the
detectors while H fixed the dependency reporting.

The fact that drove that grade:

> On `pallets/flask`, **all five** security findings the tool produced were
> false positives. Measured, not estimated — `docs/ANALYZER_ACCURACY_2026-08.md`.

**That is now fixed and re-measured.** flask produces **zero** security
findings; the 623 findings that remain are all `dead_function`, `dead_import`
and `high_complexity`. An unrelated local RL project went from 3 security
findings to 1, and the survivor is correct (its `argv[0]` is `str(PYTHON)`, so
the program being launched is not statically knowable).

`ANALYZER_ACCURACY_2026-08.md` still describes the PRE-Phase-G behaviour. It is
a dated study, not a live status page — read it as history and read this
section for current state.

### Git state at handover

| | |
|---|---|
| Current branch | `main` |
| Pushed? | **Yes** — Phase G merged to `main` and pushed |
| Working tree | Clean |
| `fix/dev-launcher-cors` | merged and deleted |

---

## 2. What is DONE (verified by running it, not by reading changelogs)

Phases A–H shipped. **The session column matters** — a row is evidence only for
the session that ran it, and anything older is testimony to re-check.

| Area | Evidence | Run in |
|---|---|---|
| Backend suite | `417 passed` in 101.64s | `0f899c51` |
| Fixture gate | `GATE PASSED`, 11/11 types at precision/recall 1.00 | `0f899c51` |
| Real-repo benchmark | precision 0.60, recall 1.00 (TP 6, FP 4, FN 0) | `0f899c51` |
| Frontend suite | `42 passed`, 6 files | `848e92a5` |
| Typecheck | `npm run typecheck` (`tsc -b`) exit 0, 0 errors | `848e92a5` |
| Playwright e2e | `17 passed` across 3 projects | `848e92a5` |
| Production build | built in 4.49s | `a55eaf1f` |
| Live API | `OPTIONS /scan` 200, `POST /scan` 200 with a real `scan_id` | `a55eaf1f` |
| CI on disk | `.github/workflows/ci.yml` (15.9 KB) + `release.yml` | `a55eaf1f` |
| Deploy files on disk | `Caddyfile`, `docker-compose.prod.yml`, both Dockerfiles | `a55eaf1f` |

**Phase G shipped in session `0f899c51`** — five commits, merged to `main`:

| Commit | What |
|---|---|
| `9691e0c` | S1 — resolve the call target; `app.run()`, `self.run()` no longer Command Injection |
| `193ff23` | S2 — SQL detectors gate on statement shape, not a bare verb |
| `f54df2c` | S3 — list argv judged by `argv[0]`; `["git", *args]` safe, `["sh","-c",user]` not |
| `01b0585` | corpus fixture `f9_detector_precision` + `command_injection` promoted to the no-FP list |
| `35c044b` | kept Phase C's all-constant rule alongside `argv[0]` |

Two departures from the plan as written, plus a fourth defect that was not in
it — all recorded in `DECISIONS.md` **D14**. Read D14 before touching these
detectors; the reasoning is not obvious from the code.

Earlier that session, the dev launcher (commit `03dccba`). Vite had
`port: 8080` but no `strictPort`, so a busy port sent it silently to 8081, which
put the browser on an origin outside the CORS allowlist — every API call died at
the preflight with a bare `OPTIONS /scan 400` in the log. `strictPort: true` now
makes that a loud failure, `start.bat` pre-checks both ports, and two tests pin
the Vite port to the backend allowlist.

---

## 3. What is NEXT — the phase order

Full detail, including acceptance criteria and idea IDs, is in
`docs/STAFF_AUDIT_2026-08-19.md` Phase 4. Summary:

| Phase | Scope | Blocks |
|---|---|---|
| ~~**G**~~ | ~~Detector truth~~ — **DONE**, session `0f899c51` | unblocked M, L |
| ~~**H**~~ | ~~Dependency truth~~ — **DONE**, session `0f899c51` | — |
| **I** | ~~Sidebar defect (F2)~~ **DONE** `848e92a5` · **F1 light/dark theming still open** | — |
| **J** | Explanation UX — F4, F5, F6, F7, F8, F9, F15 | — |
| **K** | Language contract — B6, F10 | — |
| **L** | Dead-code wiring (S8), fixture exclusion (S9), bundle split (F11) | now unblocked |
| **M** | Deploy | now unblocked |

**The next unstarted item is F1** — light mode plus a toggle, the remaining
half of Phase I. It moves the dark palette off `:root` into `.dark` /
`[data-theme]`, adds a provider, persists the choice and honours
`prefers-color-scheme`. Treat it as its own piece of work: it changes the
token architecture in `index.css` that every component reads from, so it is
not a small edit.

Or jump to **M** (deploy) — nothing blocks it. **J** is the highest-value
remaining phase for the product's positioning. There are no open *defects*.

Phase H shipped in the same session as G:

| Commit | What |
|---|---|
| `3f062f7` | S7 — a constraint is never stored in a version field |
| `3f0b6d6` | S6 — `requirements.lock` / `uv.lock` / `poetry.lock` resolve unpinned deps |
| `44e3456` | S5 — every dependency carries `checked` / `unreachable` / `skipped` |
| `e147e38` | latest-release lookup no longer requires a known installed version |

**`DECISIONS.md` D15 explains why flask now shows `unknown` for all 8
dependencies and why that is correct, not a regression.** D16 records that
`tsc --noEmit` checks nothing here.

### Phase G's acceptance criteria, and what they measured

Kept here because they are the template for judging the phases that follow.

| Criterion | Result |
|---|---|
| `pytest backend/tests -q` ≥ 329 | **373 passed**, 0 failed |
| re-scan flask → 0 security findings | **0** (was 5, all false positives) |
| re-scan the RL project → 0 SQL Injection | **0**; command injection also 3 → 1 |
| fixture gate holds | `GATE PASSED`, 11/11 types at 1.00 |

The new fixture was additionally run against the pre-Phase-G analyzer and fails
it (`command_injection` 0.38, `sql_injection` 0.50, exit 1). **Do this for every
future gate you add** — a fixture that passes both before and after a fix is
measuring nothing, which is precisely how the gate read 1.00 across the board
while every security finding on flask was wrong.

---

## 4. Traps that already cost time — do not rediscover these

- **Interpreter is `venv\Scripts\python.exe` at the repo root**, not
  `backend/venv`. Global Python 3.13 has no fastapi and dies at collection.
- **No Docker on this machine.** The GitHub runner has it and `ci.yml` has a
  `deploy-stack` job that boots the compose stack. Container claims get verified
  in CI, never locally.
- **The Bash tool's working directory persists between calls.** A `cd frontend`
  silently breaks a later repo-root command. Use absolute paths.
- **Zero-byte junk files keep appearing in the repo root.** Unquoted `(` or `)`
  in a bash command is one cause — the stray `390.52` is a captured Vite bundle
  size. But session `0f899c51` produced `1.0`, `bool`, `str` and `analyzer`
  without any unquoted parens, so something else in the toolchain also does it.
  **Run `git status --short` after every commit** and delete what appears. This
  is survivable only because explicit-path staging is mandatory here; `git add
  -A` would have committed all four.
- **Run `npx vite` from `frontend/`, never the repo root** — the root resolves a
  different Vite major than the pinned 5.4.21.
- **`tsc --noEmit` typechecks NOTHING here and exits 0.** `frontend/tsconfig.json`
  is solution-style — `"files": []` plus `references` — so the command compiles
  an empty program and reports success. Use **`npm run typecheck`** (`tsc -b`),
  which is what `ci.yml` runs. Session `0f899c51` was handed a green
  `tsc --noEmit` and `tsc -b` then found 6 real type errors in the same tree.
- **Exclude `backend/app/.cache/` from greps.** It holds cached scan JSON and a
  careless recursive grep returns megabytes.
- **Never `pip install` analysis tools into the project venv.** Use a throwaway
  venv; changing dependency resolution invalidates every later test result.
- **`git add -A` is banned here** — the tree carries gitignored `.env` and stray
  junk. Always stage explicit paths.

---

## 5. BUG-001 — CLOSED 2026-08-20

**The sidebar disappeared in a half-width browser window.** Root-caused, fixed
and verified in session `848e92a5` (`8ce9a3e`). Full write-up, including the
measurement table, in `docs/bugs/BUG-001-sidebar-split-view.md`.

One line of it: `useIsMobile()` listened to `(max-width: 767px)` but stored
`window.innerWidth < 768` — one breakpoint written two ways, and viewport
widths are fractional under Windows display scaling while `innerWidth` is
rounded. The hook now uses `(min-width: 768px)`, the exact query Tailwind's
`md:` emits, and reads `event.matches`.

**The transferable lesson:** headless Chromium was correct at every integer
width 320–1440 on all 15 routes. jsdom, Playwright viewports and the devtools
device toolbar are all whole-pixel. A layout bug that lives at fractional
widths is invisible to all of them — it took a headed window at
`devicePixelRatio` 1.25 swept one pixel at a time. If a UI bug will not
reproduce, check whether your tooling can even express the condition.

---

## 6. Strategic direction (decided, revisit only with the user)

Do **not** compete on raw detection — Semgrep, CodeQL and Sonar are free on
public repos and more precise. The durable differentiator is the **explanation
and trust model**: deterministic findings, labelled sources, trust boundaries,
confidence values, and honestly documented analysis limits.

Reposition as an **explainable repository health report**. Lead with health,
complexity, structure, dependencies and duplication. Demote security to a
clearly labelled "candidates to triage" section with the precision numbers
published openly. Phase J exists to serve this.

---

## 7. Session-end ritual

Before ending any session, update this file's section 1 and section 3, append to
`docs/DECISIONS.md` if a real decision was made, and note which model made it.
Five lines is enough. This is the cheapest habit available and the one that
stops the next session starting cold.
