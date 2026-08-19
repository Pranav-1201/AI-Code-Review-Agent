# HANDOVER — read this first, every session

**Purpose:** this file is the entry point. If you have been told something as
short as *"finish my project"*, this file is the whole brief. Read it, then
`docs/CONSTRAINTS.md`, then start at the next unfinished phase below.

**Last updated:** 2026-08-19 · **Updated by:** Claude Opus 5 session
`a55eaf1f` · **Branch at handover:** `fix/dev-launcher-cors` (2 commits ahead of
`main`, **unpushed**)

---

## 1. Where things stand right now

The project is an AI code review agent: you give it a public repository URL, it
clones it, runs a deterministic AST analysis, and returns a health report.

**Status: strong MVP, not deployable yet.** Graded **6.5/10** in
`docs/STAFF_AUDIT_2026-08-19.md`. The engineering around the product is good
(security 8, tests 8, docs 8). The analyzer's precision is not (correctness 4).

The single most important fact to carry into any work here:

> On `pallets/flask`, **all five** security findings the tool produced were
> false positives. This was measured, not estimated — see
> `docs/ANALYZER_ACCURACY_2026-08.md`.

### Git state at handover

| | |
|---|---|
| Current branch | `fix/dev-launcher-cors` |
| Commits ahead of `main` | 2 (`03dccba` launcher/CORS fix, `06de9fc` audit docs) |
| Pushed? | **No.** Nothing has been pushed. |
| Working tree | Clean |
| `main` | `00a11a6`, in sync with `origin/main` |

**First thing to decide with the user:** merge `fix/dev-launcher-cors` into
`main` and push, or keep stacking work on the branch. Do not push without
asking — pushing is outward-facing.

---

## 2. What is DONE (verified by running it, not by reading changelogs)

Phases A–F shipped before this session. Verified this session by execution:

| Area | Evidence |
|---|---|
| Backend suite | `326 passed` in 22.89s |
| Frontend suite | `39 passed`, 5 files |
| Typecheck | `tsc --noEmit` exit 0 |
| Production build | built in 4.49s |
| Live API | `OPTIONS /scan` 200, `POST /scan` 200 with a real `scan_id` |
| CI on disk | `.github/workflows/ci.yml` (15.9 KB) + `release.yml` |
| Deploy files on disk | `Caddyfile`, `docker-compose.prod.yml`, both Dockerfiles |

Also fixed **this session** (commit `03dccba`): the dev launcher. Vite had
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
| **G** | Detector truth — corpus fixtures first, then S1, S2, S3 | **blocks M** |
| **H** | Dependency truth — S5 lookup status, S6 lockfiles, S7 version parsing | — |
| **I** | Sidebar defect (F2) + light/dark theming (F1) | — |
| **J** | Explanation UX — F4, F5, F6, F7, F8, F9, F15 | — |
| **K** | Language contract — B6, F10 | — |
| **L** | Dead-code wiring (S8), fixture exclusion (S9), bundle split (F11) | after G |
| **M** | Deploy | after G |

**Start at Phase G.** It is the only thing standing between this project and a
public deployment that embarrasses its author.

### Phase G, concretely

1. **Write the fixtures first.** Add corpus cases that FAIL today:
   `app.run(debug=True)` (must not be Command Injection), an f-string containing
   the word "delete" in prose (must not be SQL Injection), and
   `subprocess.run(["git", *args])` (must not be flagged).
2. Then fix, in `backend/app/services/security_analyzer.py`:
   - **S1** — resolve the call target before flagging Command Injection. Today
     it matches the bare method name `run`, so Flask's `app.run()` and a Celery
     task's `self.run()` are both reported.
   - **S2** — `visit_JoinedStr` substring-matches `select|insert|update|delete`
     in any f-string. Require SQL shape and, better, that the value reaches a
     cursor/execute sink. The taint analyzer already models that sink and this
     detector is not using it.
   - **S3** — treat `subprocess.*` with list argv and no shell as safe,
     including `[*unpacking]` and list variables.
3. **Then raise the thresholds** — do not leave a floor sitting at a value that
   ratifies the old behaviour.

**Verification for G:** `pytest backend/tests -q` → ≥329 passed; then re-scan
flask → **0** security findings, and re-scan the RL project → **0** SQL
Injection findings.

---

## 4. Traps that already cost time — do not rediscover these

- **Interpreter is `venv\Scripts\python.exe` at the repo root**, not
  `backend/venv`. Global Python 3.13 has no fastapi and dies at collection.
- **No Docker on this machine.** The GitHub runner has it and `ci.yml` has a
  `deploy-stack` job that boots the compose stack. Container claims get verified
  in CI, never locally.
- **The Bash tool's working directory persists between calls.** A `cd frontend`
  silently breaks a later repo-root command. Use absolute paths.
- **Unquoted `(` or `)` in a bash command creates zero-byte junk files** in the
  repo root. This is where the stray `390.52` file came from — it is a captured
  Vite bundle size from a build log.
- **Run `npx vite` from `frontend/`, never the repo root** — the root resolves a
  different Vite major than the pinned 5.4.21.
- **Exclude `backend/app/.cache/` from greps.** It holds cached scan JSON and a
  careless recursive grep returns megabytes.
- **Never `pip install` analysis tools into the project venv.** Use a throwaway
  venv; changing dependency resolution invalidates every later test result.
- **`git add -A` is banned here** — the tree carries gitignored `.env` and stray
  junk. Always stage explicit paths.

---

## 5. Open item handed over unsolved

**BUG-001 — the sidebar becomes unusable in a half-width browser window.**
Full trace in `docs/bugs/BUG-001-sidebar-split-view.md`. Two hypotheses were
already **falsified** — do not re-derive them:

1. A Tailwind `md` vs `MOBILE_BREAKPOINT` mismatch. There is none: the `screens`
   override is scoped to `container`, so `md` is 768px, matching the hook.
2. `SidebarRail` at `z-20` overlapping the trigger. `AppSidebar` never renders a
   `SidebarRail`.

**Reproduce before fixing**, at a viewport of roughly 940–960px.

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
