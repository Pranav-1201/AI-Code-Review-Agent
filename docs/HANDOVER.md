# HANDOVER — read this first, every session

**Purpose:** this file is the entry point. If you have been told something as
short as *"finish my project"*, this file is the whole brief. Read it, then
`docs/CONSTRAINTS.md`, then start at the next unfinished phase below.

**Last updated:** 2026-08-24 · **Updated by:** Claude Opus 5 session
`b5a36f9d` · **Branch at handover:** `main` — J2 **merged** (`568bf4e`), branch
deleted, pushed, **CI green on the merge commit** (run `32699574335`).

> **J1 is COMPLETE, reviewed and MERGED into `main` at `37f0060`.** Branch
> deleted. `main` = `origin/main` = `e857e0e`, and **CI is green on it** (run
> `32357489001`). An earlier version of this file claimed `main` was 16 commits
> ahead of `origin/main` with CI never run — both halves were false by the time
> anyone read them, and the correction cost a session's first ten minutes.
>
> **J2 is COMPLETE and MERGED into `main` at `568bf4e`** (PR #3, 10 commits,
> branch deleted). All 6 tasks landed, each individually review-clean; the final
> whole-branch review (Opus) returned **SHIP WITH FIXES**, and the two Important
> findings plus three minors were closed in one fix wave at `e88f255`. CI is
> green on the merge commit (run `32699574335`), and `main` = `origin/main`.
>
> **Verified in that session, every command run fresh:** pytest **432 passed /
> 0 failed**, vitest **70 passed / 11 files**, `tsc -b` exit 0, `npm run build`
> succeeds, Playwright **23 passed**. Plus the acceptance row that actually
> matters: sweeping every first-party `.py` under `backend/` through the shipped
> analyzer gave **31 findings across 14 files, 31 carrying real source, 0
> placeholders**.
>
> The full task-by-task record — every ruling, every deferred minor, and three
> reviewer seats that died without reporting — is in
> `docs/superpowers/records/2026-08-24-j2-execution-record.md`.
>
> **Note for future phases:** that record lives under `docs/` on purpose.
> Execution ledgers are written to `.superpowers/sdd/<plan>/progress.md`, which
> `.superpowers/sdd/.gitignore` ignores with a bare `*` — so they never enter
> git and vanish on a clean. J1's handover pointed at its ledger and the file
> was already gone by the next session. Copy the ledger into
> `docs/superpowers/records/` before deleting the workspace.
>
> **J3 is DONE and merged** at `2004639`. Its execution record — six defects
> the reviews found in J3's own plan, and the ruling on each — is at
> `docs/superpowers/records/2026-08-25-j3-execution-record.md`. Phase J is
> finished.
>
> **J3's last open bar is now CLOSED (2026-08-26).** It read: *nobody has run a
> real scan and opened the File Analysis page; every J3 number came from
> fixtures and demo data, so the change-record line numbers are unproven
> against a real clone.* Done this session, end to end: a real clone of
> `pypa/sampleproject` through the running backend, then the real page driven
> in a real browser. All **11 change records across 4 files land on the exact
> right lines**, including `noxfile.py` with 6 insertions where an off-by-one
> would accumulate — hand-checked against `improved_code` line by line. The
> page reported *"21 changed lines highlighted"*, which is 3x6 docstring +
> 3x1 return-hint, and the highlight band sat on improved lines 24–30 exactly.
> `ast.parse` accepted all 10 code payloads (5 files x original/improved).
> Zero console errors. **There is no longer an unproven J3 claim.**
>
> **Next: F1** (light mode), **K** (language contract), **L** (S8 dead-code
> wiring is the substantive one) or **Phase M** (deploy).

---

## 1. Where things stand right now

The project is an AI code review agent: you give it a public repository URL, it
clones it, runs a deterministic AST analysis, and returns a health report.

**Status: strong MVP. Phases G, H, I-partial, J1 and J2 done; F2 (the last open
defect) fixed; not yet deployed.** Graded
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
| Current branch | `main` — `33429f8`, the `--no-ff` merge of `fix/broken-clone-cache`, pushed 2026-08-26 |
| Pushed? | **YES** — `main` is pushed and level with `origin/main`. Check CI for the newest SHA, not for any older merge commit. |
| `fix/broken-clone-cache` | merged at `33429f8`, branch deleted. CI run `32900636037` |
| `phase-j/j3-code-panes` | merged (`2004639`), CI green (run `32855931620`, all jobs), branch deleted |
| Working tree | Clean |
| `fix/dev-launcher-cors` | merged and deleted |
| `phase-j/j1-explanation-parity` | merged (`37f0060`) and deleted |
| `phase-j/j2-finding-detail` | merged (`568bf4e`) and deleted, remote ref pruned |

---

## 2. What is DONE (verified by running it, not by reading changelogs)

Phases A–H shipped. **The session column matters** — a row is evidence only for
the session that ran it, and anything older is testimony to re-check.

| Area | Evidence | Run in |
|---|---|---|
| Backend suite | `440 passed`, 0 failed | `e4ebf578` (J3) |
| Frontend suite | `98 passed`, 15 files | `e4ebf578` (J3) |
| Typecheck | `npm run typecheck` (`tsc -b`) exit 0 | `e4ebf578` (J3) |
| End-to-end | `26 passed`, 0 failed, 3 projects | `e4ebf578` (J3) |
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
| Backend suite | `432 passed, 0 failed` — **on merged `main`** | `b5a36f9d` |
| Frontend suite | `70 passed`, 11 files — **on merged `main`** | `b5a36f9d` |
| Typecheck | `npm run typecheck` (`tsc -b`) exit 0 — **on merged `main`** | `b5a36f9d` |
| Playwright e2e | `23 passed` across 3 projects | `b5a36f9d` |
| Production build | built in 5.85s | `b5a36f9d` |
| Snippets carry real source | swept every first-party `.py` under `backend/`: 14 files with findings, **31 findings, 31 with real source, 0 placeholders** | `b5a36f9d` |
| Backend suite | `444 passed, 0 failed` in 39.58s (440 + 4 new) | `d0a60ab7` |
| **J3 bar: real scan → real page** | real clone of `pypa/sampleproject`, driven in a real browser: **11/11 change records on the exact right lines**, "21 changed lines highlighted" = 3x6+3x1, highlights on improved lines 24–30, 0 console errors | `d0a60ab7` |
| Improved code is valid Python | `ast.parse` on all 10 payloads (5 files x original/improved): **10 ok, 0 bad** | `d0a60ab7` |
| Broken-cache fix, real data | flask went from `git fetch` exit 128 to a clean **41s** scan through the browser; its cache came back with `HEAD` + `config` | `d0a60ab7` |
| `start.bat` wait loop | new loop measured **39s** worst case against dead ports (was 60 iterations at the same 3.25s each) | `d0a60ab7` |

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
| ~~**J**~~ | Explanation UX — **COMPLETE and merged**. J1 (F7, F8, F9-detail, F15), J2 (F6, F9, `snippet`, F16) at `568bf4e`; **J3 (F4, F5) merged 2026-08-25 at `2004639`**, CI green | — |
| **K** | Language contract — B6, F10 | — |
| **L** | Dead-code wiring (S8), fixture exclusion (S9), bundle split (F11) | now unblocked |
| **M** | Deploy | now unblocked |

**The next unstarted item is F1** — light mode plus a toggle, the remaining
half of Phase I. It moves the dark palette off `:root` into `.dark` /
`[data-theme]`, adds a provider, persists the choice and honours
`prefers-color-scheme`. Treat it as its own piece of work: it changes the
token architecture in `index.css` that every component reads from, so it is
not a small edit.

Or jump to **M** (deploy) — nothing blocks it.

### Known open, none of them blocking

| Item | Where | Note |
|---|---|---|
| `generate_improved_code` is a dead switch | `settings_manager.py` | stored and rendered in Settings, read by nothing; the transforms run unconditionally. Changing it alters scan behaviour — its own change. See `DECISIONS.md` D16-area note. |
| `WhatChangedPane`'s `return null` is unreachable | `frontend/src/components/WhatChangedPane.tsx` | found by J3 review, recorded, judged not worth a change on its own. |
| "Cannot reach backend … (Failed to fetch)" | `frontend/src/lib/api.ts` `startScan` | **NOT reproduced** on 2026-08-26 across four repos in a real browser. Leading unproven candidate: `API_BASE` is `http://localhost:8000` while uvicorn binds `127.0.0.1` only, so a browser resolving `localhost` → `::1` gets a refusal with exactly that wording. `DECISIONS.md` D18. Needs the failure captured on the machine that shows it — do not "fix" it blind. |
| Orphan listener on 8000 | — | a socket answering HTTP 200 whose PID `taskkill` cannot find. `start.bat`'s port-clash message will suggest a `taskkill` that fails. Reboot clears it. |

**~~One J3 bar was never met~~ — MET 2026-08-26, session `d0a60ab7`.** It read:
nobody has run a real scan and opened the File Analysis page, so the
change-record line numbers are unproven against a real clone. Done: real clone
of `pypa/sampleproject`, real backend, real browser. 11/11 change records on the
exact right lines across 4 files, `noxfile.py` (6 insertions) included. See the
evidence rows in section 2. **Nothing about J3 is unproven any more.**

**The equivalent bar for whatever ships next:** run it against a real clone
through the real UI before believing it. Two of this session's three findings —
the exit-128 broken cache and the launcher's three-minute stall — were invisible
to a fully green 440-test suite and surfaced the moment the app was actually
driven. The suite is not the acceptance criterion; the running app is.

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
- **A cached clone can exist and still not be a git repository.** Fixed
  2026-08-26: an interrupted eviction leaves `.git` holding `objects/`, `refs/`,
  `logs/` and `index` but no `HEAD` and no `config`. The old gate was
  `os.path.isdir(.git)`, so the incremental branch ran `git fetch` on it and
  died with exit 128 — **permanently** for that repo, because nothing ever
  cleared the directory. Three of twelve cached clones were in that state, one
  of them flask. `main._usable_cached_clone` now asks git via `rev-parse
  --git-dir` and a rejected cache falls through to the self-healing full clone.
  If you see a raw `CalledProcessError` repr reach the UI, this is the shape.
- **`start.bat` reporting a port clash can hand you a dead end.** It prints
  `taskkill /F /PID <pid>` from netstat's PID column; on 2026-08-26 that PID had
  no process (`taskkill` said "not found") while the socket still answered HTTP
  200. Not diagnosed further — if it recurs, do not trust the suggested command.
- **A backend can hold port 8000 and never answer HTTP.** Measured 2026-08-26
  from a `start.bat`-launched backend: connect in 0.02s, no response in 60s.
  Probing with curl is right to call that not-ready; the old wait loop then held
  the browser ~3 minutes. Now bounded to 12 iterations (39s measured).
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
