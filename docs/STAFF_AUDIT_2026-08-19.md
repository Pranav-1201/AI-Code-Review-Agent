# Staff-level audit & deployment roadmap — AI Code Review Agent

**Date:** 2026-08-19 · **Auditor pass:** single session · **Scope:** audit + plan only, no code written
**Repo:** `D:\ETPROJECT` (= `github.com/Pranav-1201/AI-Code-Review-Agent`) at `00a11a6`

---

## PHASE 0 — Ground truth

### Prior documents found (treated as done, not re-audited)

| Document | Status |
|---|---|
| `docs/SYSTEM_AUDIT_2026-07.md` | The original 6.7/10 audit. Phases A–F have since shipped. |
| `docs/ANALYZER_ACCURACY_2026-08.md` | Written earlier **this session**. Its findings are carried forward, not re-derived. |

**Treated as DONE, verified this session by running the code — not by reading changelogs:**

- Phase A/B security hardening — `backend/app/api_guard.py` exists and is wired as
  real middleware in `main.py:100-127`; CORS rejects non-allowlisted origins
  (reproduced: `400 Disallowed CORS origin`).
- Phase C detector work — `backend/benchmark/corpus/thresholds.json` present, all
  floors 1.0. **But see F-CRIT-3: the gate is narrower than it reads.**
- Phase D frontend tests — vitest 39 passed this session.
- Phase E ops — `disk_guard.py`, `observability.py` present; 20 env vars all
  documented in a 204-line `.env.example`.
- Phase F deploy — `Caddyfile`, `docker-compose.prod.yml`, both Dockerfiles,
  `.github/workflows/ci.yml` (15.9 KB) and `release.yml` all exist on disk.

### Git state

- Branch `main`, **in sync with `origin/main`** (0 ahead / 0 behind).
- No extra worktrees.
- Uncommitted: `backend/tests/test_api_security.py`, `frontend/vite.config.ts`,
  `start.bat` (the CORS/port fix made earlier this session), plus two new
  untracked docs.
- **Repo hygiene defect:** `390.52` — a zero-byte file in the repo root. Root
  cause identified: it is the Vite bundle size `390.52 kB` captured by an
  unquoted shell redirect from a build log. Harmless but should be deleted and
  `.gitignore`d against recurrence.

### Verification run THIS session (all evidence below is from this run)

| Command | Result |
|---|---|
| `venv/Scripts/python.exe -m pytest backend/tests -q` | **326 passed**, 3 warnings, 22.89s |
| `npx vitest run` (frontend) | **39 passed**, 5 files |
| `npx tsc --noEmit` | **exit 0** |
| `npm run build` | **built in 4.49s** |
| Live `OPTIONS /scan` + `POST /scan` | 200 / 200, real `scan_id` returned |

**Environment gotchas discovered (record for implementing sessions):**

1. Python interpreter is `venv\Scripts\python.exe` at the **repo root** — not
   `backend/venv`. The global Python 3.13 lacks fastapi and dies at collection.
2. **No Docker on this machine.** The GitHub runner has it; `ci.yml` has a
   `deploy-stack` job that boots the compose stack. Any container claim must be
   verified in CI, never locally.
3. The Bash tool's working directory **persists between calls** — a `cd frontend`
   silently breaks a later repo-root command. Use absolute paths.
4. Unquoted `(`/`)` in a bash command creates zero-byte junk files in the repo
   root. This is the documented origin of `390.52`.
5. `npx vite` from the repo root installs a *different* Vite (8.x) than the
   frontend's pinned 5.4.21 — always run it from `frontend/`.
6. Never `pip install` analysis tools into the project venv; it changes
   dependency resolution. Use a throwaway venv.

---

## PHASE 1 — Comprehension

### Tech stack (detected)

| Layer | Technology |
|---|---|
| Backend | Python 3.11, FastAPI, uvicorn, Celery (eager unless broker set), SQLite (WAL) |
| Analysis | Pure-stdlib AST; iterative Tarjan SCC for call graphs (deliberately not networkx) |
| LLM | Anthropic, **gated OFF by default**, paraphrase-only — every finding is deterministic |
| Frontend | React 18 + TypeScript, Vite 5.4.21, Tailwind, shadcn/ui, Recharts |
| Infra | Docker Compose + Caddy (single origin), GHCR images, GitHub Actions |

### API surface (`main.py`) — 11 routes

`GET /` · `GET /health` · `POST /scan` · `GET /scan/{id}` · `GET /scan/{id}/stream` (SSE)
`GET /scans` · `GET|POST /settings` · `POST /settings/reset` · `POST /feedback` · `GET /feedback/precision`

Public (no key): `/`, `/health`, `/docs`, `/redoc`, `/openapi.json`. Everything
else requires `X-API-Key` when `API_KEY` is set. `OPTIONS` is exempt by design.

### Frontend architecture

18 pages, route table centralised in `lib/routes.ts` (imports nothing — good).
`DashboardLayout` wraps `SidebarProvider` + `AppSidebar` + sticky header.
Code-split: 16 lazy chunks. Entry 390.52 kB, `Visualizations` 432.04 kB,
`FileAnalysis` 133.63 kB.

### Environment inventory — 20 first-party vars, **100% documented**

`.env.example` is 204 lines and covers every variable found in app code, with
the *reasoning* for each. This is genuinely above industry norm. No gap here.

### Startup-time external requirements

None blocking. The analysis engine is fully deterministic with every gate off
(`ENABLE_ANTHROPIC`, `ENABLE_CODEBERT` default false). **No model weights, no
datasets, no absolute machine paths required at boot.** This is a significant
deployment advantage and rules out the most common P0 blocker.

### Mock/placeholder data

None found rendering as real output. `explanationSource` is `deterministic`
throughout all three sample reports — no LLM invention. `Index.tsx` is a dead
placeholder page (noted in prior memory, still true).

### Real usage artifacts analysed

Three JSON reports the tool produced (flask, RL-Project, this repo) were
compared against an independent pass using `bandit 1.9.4`, `radon 6.0.1`,
`pyflakes 3.4.0`, `vulture 2.16`. **This is measured field behaviour, and it
changed the grade materially** — see Correctness below.

---

## PHASE 2 — Grades

| Category | Score | Evidence |
|---|---|---|
| **Correctness & functionality** | **4/10** | Flask scan: **5 of 5 security findings false** (`ANALYZER_ACCURACY_2026-08.md`). `.run()` matched by bare name → `app.run()` flagged Command Injection. f-string prose matched → the word "Delete" in an error message flagged **SQL Injection, High, conf 0.8**. Dead-code findings absent from all 3 reports despite `thresholds.json` claiming 1.0. |
| **Architecture & code quality** | **7/10** | Clean layering (`analysis/` pure, `services/` orchestration, `api_guard.py` holds the whole trust boundary in one readable file). Against it: `dependency_analyzer.analyze_dependencies` CC **59**, `repository_review_engine.review_repository` CC **58** (radon, this run). |
| **Backend logic** | **7/10** | Sensible REST surface, SSE with poll fallback, typed errors. Rate limiter is **in-process** — `.env.example` itself documents that N replicas = N×limit. |
| **Frontend/UI** | **6/10** | Coherent dark aesthetic, code-split, ErrorBoundary present. **Dark-only**: `index.css:8` puts the dark palette directly on `:root`; no `.dark` class, no ThemeProvider. |
| **UX** | **5/10** | Skip-link + `main` landmark present (real a11y work). But: sidebar unusable at ~960px (user-reported, screenshot), severity tiers not clickable, issues not drillable, no language-support messaging. |
| **Security** | **8/10** | Strongest area. API-key middleware applied as middleware (not per-route, so new routes are protected by default), SSRF host allowlist, repo-URL length cap, CORS never `*`, constant-time key compare, `/health` advertises `auth: disabled`. Deduct: in-process rate limiting; API key inlined into the static bundle (documented honestly, still a limit). |
| **Performance** | **6/10** | 16 lazy chunks is real work. `Visualizations` at **432 kB** is the largest chunk and is heavier than the entry bundle. |
| **Test coverage & reliability** | **8/10** | 326 backend + 39 frontend tests, **and they run in CI on GitHub** — not just locally. `deploy-stack` job actually boots the compose stack. This is the project's second-strongest area. |
| **Documentation & DX** | **8/10** | `.env.example` at 204 explanatory lines, `DEPLOYMENT.md`, `CLAUDE.md`, per-module rationale comments. A stranger can clone and run. |
| **Deployment readiness** | **7/10** | Caddy + compose + GHCR + sha-tagged rollback + WAL-safe SQLite backups, all exercised in CI. Never run on a real host. |

### Overall: **6.5 / 10 — a strong MVP with a defective core**

The engineering *around* the product is genuinely good — better than most
projects at this stage. Security, testing, CI and documentation would pass a
real review. The problem is the product itself: **the analyzer's precision is
the one thing a code-review tool is judged on, and on a famous repo it was
wrong 5 times out of 5.**

**Three categories hold it back:** Correctness (4), UX (5), Frontend (6).
Correctness is not a polish item — it is the product.

---

## PHASE 3 — Improvement backlog

### Strategic direction (answer first)

**Who uses this?** Realistically: students and junior devs wanting a readable
health report on a repo, and Pranav as a portfolio artifact.

**Does something already do this better?** Yes, for raw detection — Semgrep,
CodeQL, SonarQube, Snyk, and GitHub's own code scanning are free for public
repos and far more precise. **Competing on detection is a losing position.**

**The durable differentiator is not the detector — it is the explanation and the
trust model.** This project's real assets: every finding is deterministic and
labelled (`explanation_source`), it states its own boundaries, it shows *why a
finding matters* and *how to fix it*, it computes a whole-repo health narrative,
and it ships a `trust_boundary` and `confidence` on each finding. Semgrep gives
you a rule ID; this gives a junior developer a lesson.

**Recommendation: reposition as "an explainable repo health report", not "a
security scanner."** Concretely:
- Lead the UI with health, complexity, structure, dependencies and duplication —
  areas where the tool is measurably competent.
- Demote security to a clearly-labelled **"candidates to triage"** section, with
  the precision numbers published honestly.
- Long-term option worth considering: keep the explanation layer and delegate
  raw detection to Semgrep/bandit, which turns the weakest component into a
  strength. (Option C below.)

Three options: **(A)** fix the detectors and keep positioning as a scanner —
highest risk, competing with CodeQL. **(B)** reposition to explainable health
report, fix the two worst detectors anyway — **recommended**. **(C)** wrap
established engines and own the explanation layer — best product, largest rewrite.

### Backlog

**Security / correctness of the product (S)**

| ID | Change | Why | Impact × Effort |
|---|---|---|---|
| S1 | Resolve `.run()` call target before flagging Command Injection | `app.run()`, `self.run()` flagged; 5/5 Flask FPs | **H × L** |
| S2 | Require SQL *shape* + a cursor/execute sink for SQL Injection, not substrings | "Delete"/"update" in prose → High/0.8 FP | **H × M** |
| S3 | Treat `subprocess.*` with list argv and no shell as safe, incl. `[*unpack]` | Phase C fix doesn't generalise past the literal-list fixture | **H × L** |
| S4 | Add real-world corpus fixtures for S1–S3 before fixing | Gate reads 1.00 while real code fails | **H × M** |
| S5 | Report OSV lookup status per dependency (`checked`/`unreachable`) | 0 CVEs everywhere is indistinguishable from a dead lookup | **H × L** |
| S6 | Read `requirements.lock` / `uv.lock` when manifests are unpinned | 8/21 deps `version: unknown` | **M × M** |
| S7 | Fix version parsing of constraints (`flit_core==3.11,<4`) | Constraint stored in a version field | **M × L** |
| S8 | Find why dead_import/dead_function never reach report JSON | 12 real unused imports in own repo, 0 reported | **H × M** |
| S9 | Exclude benchmark/fixture corpora from findings | Own deliberately-vulnerable fixtures reported as real | **M × L** |
| S10 | Move rate limiting to Redis | In-process limiter × N replicas | **M × M** |

**Backend (B)**

| ID | Change | Impact × Effort |
|---|---|---|
| B1 | Decompose `analyze_dependencies` (CC 59) and `review_repository` (CC 58) | M × H |
| B2 | Investigate the CC algorithm: reports 34 where radon reports 58 | M × M |
| B3 | Declare whether test files are included in complexity ranking; make it consistent | L × L |
| B4 | Exclude stdlib + own package from `most_reused_module` | L × L |
| B5 | Raise/justify the duplicate-similarity threshold (35% reported as "duplicate") | L × L |
| B6 | Reject unsupported languages with a clear message, not a generic error | **H × M** (user item) |

**Frontend / UX (F)** — user-reported items marked ★

| ID | Change | Impact × Effort |
|---|---|---|
| F1 ★ | Light mode + toggle. Requires moving the dark palette off `:root` into `.dark`/`[data-theme]`, adding a provider, persisting choice, honouring `prefers-color-scheme` | **H × M** |
| F2 ★ | Sidebar unusable at ~960px (split-view). **Reproduce first** | **H × M** |
| F3 ★ | Sort file list by score (asc/desc) and alphabetically, alongside the language filter | M × L |
| F4 ★ | "Improved" pane: say *"No improvements needed"* when empty; otherwise show the **full** improved file with changed regions highlighted | **H × M** |
| F5 ★ | Replace the raw patch pane with a prose explanation of *what* changed and *why* | **H × M** |
| F6 ★ | Make the 4 severity tiers clickable → scroll/anchor to that group | M × L |
| F7 ★ | Security report: explain why each alert matters, with reasoning per finding | **H × M** |
| F8 ★ | AI Suggestions: friendlier, plain-language; state the error, the fix, the what and the why | **H × M** |
| F9 ★ | Issue Explorer: issues clickable → full detail + remediation | **H × M** |
| F10 ★ | State supported languages up-front in the UI | M × L |
| F11 | Split the 432 kB `Visualizations` chunk | M × M |
| F12 | Delete the dead `Index.tsx` placeholder | L × L |
| F13 | Fix `JavaScript 0%` rounding in the language bar | L × L |
| F14 | Reconcile `healthScore` 54 vs `avg_score` 90.3 — or explain the relationship in the UI | M × L |
| F15 | Rename/clarify `security_issues` (production-only count) vs the 5 shown in the file list | M × L |
| F16 | a11y pass on new interactive elements from F6/F9 (keyboard, focus, ARIA) | M × M |

**Repo hygiene (H)**

| ID | Change | Impact × Effort |
|---|---|---|
| H1 | Delete `390.52`; gitignore zero-byte junk patterns | L × L |
| H2 | Commit or drop the 3 uncommitted working-tree files | L × L |

---

## PHASE 4 — Phased plan

### P0 — blockers before ANY public deploy

**S1, S2, S3, S4** — the false-positive classes. Non-negotiable. `.run()` and the
word "update" appear in essentially every Python codebase; a stranger's first
scan will produce visibly wrong High-severity findings.
**S5** — a report that silently claims "0 vulnerabilities" when the lookup failed
is worse than one that says "couldn't check."
**F2** — the app is unusable in a half-screen browser window.

### P1
S8, S9, B6, F1, F4, F5, F7, F8, F9, F15, S6, S7

### P2
B1–B5, F3, F6, F10–F14, S10, H1, H2

### Phases

| Phase | Scope (IDs) | Acceptance | Verification command → expected result | Sessions |
|---|---|---|---|---|
| **G — detector truth** | S4 → S1, S2, S3 | Corpus fixtures exist that fail *before* the fix and pass after; no new FPs on flask | `venv/Scripts/python.exe -m pytest backend/tests -q` → **≥329 passed**; then re-scan flask → **0 security findings**, and re-scan RL-Project → **0 SQL Injection** | 2 |
| **H — dependency truth** | S5, S6, S7 | Every dep carries a lookup status; lockfiles read | `pytest -k dependency -q` → passes; flask report shows `latestVersion` for **8/8** deps, no `"3.11,<4"` in a version field | 1 |
| **I — sidebar + theming** | F2, F1, F16 | Sidebar operable 320–1920px; light/dark toggle persists and respects `prefers-color-scheme` | `npx playwright test` at viewport 960×800 → sidebar toggles; `npx vitest run` → green | 2 |
| **J — explanation UX** | F4, F5, F7, F8, F9, F6, F15 | Empty improved-pane states; full improved code with highlights; clickable tiers and issues | `npx vitest run` → green with new tests per component; manual click-through recorded | 3 |
| **K — language contract** | B6, F10 | A MATLAB-only repo returns a clear "unsupported language" message, not a stack trace | `POST /scan` a MATLAB repo → **422** with a readable message; UI renders it | 1 |
| **L — wiring + hygiene** | S8, S9, F11–F14, H1, H2 | Dead-code findings appear; fixtures excluded; bundle reduced | Re-scan this repo → **≥12** dead_import findings, **0** from `benchmark/corpus/fixtures/`; `npm run build` → Visualizations chunk **< 250 kB** | 2 |
| **M — deploy** | infra | Live on a real host with TLS, monitoring, backups, and a **drilled** rollback | `curl https://<domain>/health` → 200 with `auth: enabled`; roll back to prior sha and confirm 200 again | 1–2 |

**Sequencing:** G blocks M (do not deploy known-wrong detectors). G blocks H
only loosely — H can run in parallel. I and J are frontend-only and can run in
parallel with G/H. K depends on nothing. L should follow G (S9 touches the same
filtering path). M is last.

### Deployment recommendation

**Recommended: a single small VPS (Hetzner CX22 or DigitalOcean basic droplet),
running the compose stack behind Caddy that already exists.**

- **Rationale:** the architecture is already built for exactly this — `Caddyfile`,
  `docker-compose.prod.yml`, sha-tagged GHCR images, SQLite with WAL backups, and
  a CI job that boots the whole stack. Nothing needs re-architecting. Critically,
  `/scan` runs `git clone` and CPU-heavy AST analysis with **no external model or
  dataset needed at boot**, which suits a plain VM and rules out serverless
  (long-running jobs, disk cache, and the LRU eviction in `disk_guard.py` all
  assume persistent local disk).
- **Cost:** ~**$5–7/month** (Hetzner CX22 ≈ €4.5; DO basic ≈ $6) + domain ~$12/yr.
  GHCR is free for public images. Verify current pricing before committing —
  these figures are from general knowledge, not checked this session.
- **Alternative 1 — Fly.io:** nice DX and free TLS, but a persistent volume is
  needed for the clone cache and scaling to >1 machine breaks the in-process rate
  limiter (S10) and the shared SQLite assumption. ~$5–10/mo.
- **Alternative 2 — Render/Railway:** simplest, but ephemeral disk defeats the
  clone cache and eviction design, and cold starts hurt a long scan. ~$7–20/mo.
- **Rejected — Vercel/Netlify/Lambda:** execution time limits and no persistent
  disk make them structurally wrong for this workload.

Phase M must cover: CI hookup (`release.yml` already publishes sha-tagged
images), `SITE_ADDRESS` + `API_KEY` + `VITE_SITE_URL` set, Caddy auto-TLS (ports
80 **and** 443 open for HTTP-01), Sentry DSN set, `BACKUP_HOST_DIR` on the host
filesystem, and a rollback drilled once by setting `IMAGE_TAG` to a prior sha.

---

## Rules for implementing sessions

1. **One PR per plan row.** Never bundle two IDs.
2. **Suite green at every checkpoint** — `pytest` + `vitest` + `tsc` + `build`.
3. **Stop at phase boundaries** for review. Do not roll into the next phase.
4. **Commit with explicit file paths.** Never `git add -A` (this repo has
   untracked junk and gitignored `.env`).
5. **Additive checkpoints for any restructure:** new code added and verified
   green *before* old code is removed. The tree never goes red.
6. **Leave uncommitted work untouched** unless the task is to commit it.
7. **No AI attribution** in commits, PRs, tags or releases (`CLAUDE.md`).
8. **Every "done" needs fresh evidence from that session** — command + output.
   Prior notes are testimony, not evidence.
9. **For F2 specifically: reproduce before fixing.** Two hypotheses were already
   falsified this session — (a) a Tailwind `md` vs `MOBILE_BREAKPOINT` mismatch
   (there is none; `screens` is scoped to `container`, so `md` = 768 = the hook's
   breakpoint), and (b) `SidebarRail` z-20 overlapping the trigger (`AppSidebar`
   never renders a `SidebarRail`). Do not re-derive these. Start by reproducing at
   ~940–960px viewport width.

---

## Open question for the next session

`F1` (light mode) changes `index.css` token architecture, which every component
inherits. Decide up front whether to use a `.dark` class (Tailwind
`darkMode: "class"`) or `[data-theme]` attributes — retrofitting the other way
later touches every file again.
