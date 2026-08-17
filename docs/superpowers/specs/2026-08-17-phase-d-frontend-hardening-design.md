# Phase D — Frontend Hardening

**Date:** 2026-08-17
**Status:** Approved, ready for implementation planning
**Branch:** `phase-d/frontend-hardening`
**Baseline:** `bf8b084` on `main` (CI green, run 31971128322)

## Context

The 2026-08 audit graded this project 6.7/10 and laid out phases A–G. Phases A
(security hardening), B (CI + release), and C (detector precision) are merged to
`main` and green. Phase D is the frontend's turn.

The frontend today has:

- **zero test files** of its own — `package.json` wires `vitest`, and
  `tsconfig.app.json` even declares `"types": ["vitest/globals"]`, but nothing
  consumes either. CI carries an explicit comment explaining why there is no
  `npm test` step: vitest exits non-zero when it finds no tests.
- **zero `React.lazy`** — all sixteen routes, including the ones pulling
  `recharts`, `react-markdown`, and the dependency graph renderer, are in the
  entry chunk.
- **zero error boundaries** — any render-time throw white-screens the entire
  application, taking the sidebar and navigation with it.
- **no mobile verification** of any kind.

Phase A4 is the cautionary tale that motivates most of this. A backend field had
always been shipped as `{id, summary, severity}` objects while `types.ts`
declared `string[]`; `DependencyAnalysis.tsx` rendered each entry directly as a
React child, which throws. The Dependency page therefore crashed on any real CVE.
It survived undetected because PyPI CVEs are rare, the response mapper is `any`
-typed so `tsc` could not see it, and — decisively — the typecheck that should
have caught it **was compiling zero files**: the root `tsconfig.json` is
solution-style (`"files": []` plus project references), so `tsc --noEmit` exits 0
unconditionally.

Three independent safety nets were absent at once. Phase D installs them.

## Goals

1. A real unit test harness, with the response mapper — the widest untyped
   boundary in the frontend — as its first subject.
2. An error boundary, so a single page's throw stops being an application-wide
   outage.
3. Route-level code splitting, so the entry bundle stops carrying every chart
   library in the project.
4. An end-to-end smoke test that exercises the production build.
5. Automated mobile-viewport assertions that survive as a regression gate.
6. All of the above wired into CI, where they gate `main`.

## Non-goals

- Any backend change. Backend behaviour stays covered by the 288 pytest tests.
- Visual or aesthetic redesign. This phase asserts the UI is not *broken* at
  narrow widths; it does not judge whether it is attractive.
- Component-level tests for the sixteen page components. Pages depend on
  `ScanContext`, `SidebarProvider`, and the router, so testing them in isolation
  costs far more scaffolding than it returns. The E2E smoke covers their render
  path against the real build instead.
- Multi-user auth, HTML/PDF export, or anything else deferred to phase G.

## Decisions

These four were put to the repository owner and answered on 2026-08-17.

### E2E gets a mocked API, not a live backend

Playwright intercepts every backend call with `page.route` and fulfills from
fixtures. The alternative — booting `uvicorn` in CI and scanning a real
repository — proves the true contract but needs a `git clone` per run, costs
minutes, and is the textbook source of flaky CI.

The accepted cost is that **mocks can drift from the real backend contract**.
Two things bound that risk: the backend contract is independently covered by the
pytest suite, and the fixtures are derived from the actual response shapes read
out of `response-mapper.ts` and `api.ts` rather than invented.

### The mobile pass produces assertions, not screenshots

Playwright loads every route at 375px and 768px and asserts no horizontal
overflow. A screenshot review would catch "ugly but not broken", which
assertions cannot — but a screenshot review is a one-time audit that stops
protecting anything the moment it finishes. A permanent gate was preferred.

### Every route is lazy except `/`

`RepositoryScanner` is the landing route and stays eager, so first paint never
shows a loading fallback. The other fifteen become `React.lazy`.

### Vulnerable devDependencies are bumped as part of this phase

The live OSV scan run during Phase A4 found four vulnerable direct npm
dependencies, none remediated: `vitest` 3.2.4 (Critical, GHSA-5xrq-8626-4rwp),
and `react-router-dom` 6.30.3 / `postcss` 8.5.6 / `vite` 5.4.21 (High).

Phase D makes `vitest` load-bearing, so shipping a new test suite on a
Critical-CVE runner would be backwards. The build/dev-time packages are bumped
here in their own commit.

`react-router-dom` is deliberately **excluded**: it is a runtime dependency that
`App.tsx` imports directly, and this phase is already rewriting `App.tsx`'s
routing. Changing the router and the router's library in the same phase would
make a regression ambiguous. It carries forward to phase E.

**Amended 2026-08-17, after checking the registry.** This decision was taken on
the assumption that all three build-time bumps were in-range patches. Two are:
`vitest` 3.2.4 → **3.2.7** and `postcss` 8.5.6 → **8.5.26**. `vite` is not —
`npm audit` reports its only fix as **8.2.1**, three majors up from 5.4.21, and
flags it `isSemVerMajor`.

`vite` is therefore **also deferred to phase E**. Two reasons: a three-major
build-tool migration is not a patch and deserves its own verification, and it
would move the chunk-output baseline that this phase's code-splitting evidence
is measured against. The High advisory stands, recorded and unremediated, and
it is a dev/build-time exposure rather than one in the shipped static bundle.

For the same reason the bumps must be **targeted, one package at a time**.
A blanket `npm audit fix` resolves `react-router-dom` too, against this
section's own decision.

## Design

### 1. Test harness

The `test` block is added to the existing `frontend/vite.config.ts`, importing
`defineConfig` from `vitest/config` (which re-exports Vite's own). The
alternative — a separate `vitest.config.ts` — would require a second copy of the
`@` path alias, and two copies of a path alias drift.

Configuration:

| Setting | Value | Reason |
|---|---|---|
| `environment` | `"jsdom"` | DOM APIs for `@testing-library/react` |
| `globals` | `true` | `tsconfig.app.json` already declares `vitest/globals`; this makes that declaration true rather than dangling |
| `setupFiles` | `./src/test/setup.ts` | imports `@testing-library/jest-dom/vitest` for the DOM matchers |
| `include` | `src/**/*.test.{ts,tsx}` | **Load-bearing.** Vitest's default glob would collect `e2e/*.spec.ts`, where Playwright's `test` and `expect` are different objects from vitest's. The two harnesses must not see each other's files. |

`src/test/setup.ts` is new and contains only the matcher import.

### 2. Response mapper unit tests

`src/lib/response-mapper.test.ts`. `mapApiResponse` is ~130 lines of pure
function with no I/O and no mocking requirement, sitting on the widest untyped
boundary in the application — the best value per line of test in the repository.

Cases, in priority order. The first two are regressions of defects already
documented in the file's own comments:

1. **Backend zero must not win.** `summary.average_quality_score` of `0` is not
   nullish, so `??` would accept it and mask real production scores. The code
   guards with `typeof backendAvg === "number" && backendAvg > 0`; a test pins
   that a zero falls through to recomputation from production files, and that a
   positive value is trusted.
2. **Legacy vulnerability strings coerce.** `normalizeVulnerabilities` turns a
   bare CVE id string into `{id, summary: "", severity: "Unknown"}`. Scans
   persisted before OSV enrichment replay through the history page; a raw string
   reaching the renderer is what crashed the Dependency page.
3. **Field-name fallback chains** resolve in the documented precedence:
   `file_reports` → `reports` → `files`, and `repository_summary` → `summary`.
4. **Severity mapping**: `"moderate"` maps to `Medium`; `"Info"` is preserved
   and not collapsed to `Low` (deliberate, so the UI can show realistic
   exploitability); unknown input floors to `Low`.
5. **Production-only filtering**: the `securityIssues` fallback counts
   production files only, not test or non-code files.
6. **Path normalization**: backslashes become forward slashes.
7. **`getDisplayName`**: returns the bare basename when unique, and
   `parent/basename` when two files collide.
8. **Degenerate input**: `{}` and missing arrays produce a valid `ScanReport`
   rather than throwing.

These are characterization tests over code that already exists and already
ships. Where a test reveals behaviour that looks wrong, the finding is
**reported, not silently corrected** — a behaviour change smuggled inside a
commit labelled "add tests" is exactly how a regression hides.

### 3. Error boundary

`src/components/ErrorBoundary.tsx`, a class component (React offers no hook
equivalent) using `getDerivedStateFromError` for the fallback state and
`componentDidCatch` for logging.

It is mounted **inside** `DashboardLayout`, wrapping `<Routes>` — not at the
root. Placement is the whole design decision: at the root, a page crash takes
the sidebar and header with it and the user's only recourse is the browser back
button. Inside the layout, the chrome survives and the user can navigate away
from the broken page unaided.

The fallback offers a "Try again" that resets the boundary's state and a link
back to `/`.

Test: `src/components/ErrorBoundary.test.tsx` renders a child that throws and
asserts the fallback appears in place of it. React logs caught errors to
`console.error` by design, so the test silences that channel for the duration
rather than letting expected noise pollute the run.

### 4. Route code splitting

`App.tsx`: the fifteen non-landing route components become `React.lazy`
imports, wrapped in a single `<Suspense>` placed inside the error boundary — so
that a chunk that fails to load surfaces as the boundary's fallback rather than
an unhandled rejection.

Evidence is the `vite build` chunk manifest before and after. The claim being
tested is that `recharts`, `react-markdown`, and the dependency-graph code leave
the entry chunk. A build whose entry chunk did not shrink means the splitting
did not work, regardless of what the source looks like.

### 5. E2E and mobile specs

`frontend/playwright.config.ts` plus `frontend/e2e/`.

The `webServer` block runs `vite preview` against the **production build**, not
the dev server. This is deliberate: the dev server serves unbundled modules, so
it would not exercise the lazy chunks that item 4 just created.

Every backend call is intercepted. The routes to mock, read off `api.ts`:

| Route | Method | Fulfilled with |
|---|---|---|
| `/scan` | POST | `{scan_id}` |
| `/scan/:id/stream` | GET | `text/event-stream`, a progress frame then a complete frame |
| `/scan/:id` | GET | polling status, terminal `complete` |
| `/scans` | GET | history rows |
| `/settings` | GET | settings object |

`api.ts` prefers SSE via `EventSource` and falls back to polling on any stream
failure. The mock therefore fulfills the stream route for real. **If SSE
fulfillment proves flaky under CI**, the documented fallback is to fulfill that
route with 404 and let the existing polling path carry the test — `api.ts`
already handles exactly this case, and `/scan/:id` is mocked regardless.

- `e2e/smoke.spec.ts` — load `/`, submit a repository URL, assert results
  render, then navigate through three routes to prove lazy chunks resolve.
- `e2e/mobile.spec.ts` — every route at 375px and 768px, asserting
  `document.documentElement.scrollWidth <= clientWidth` and that the sidebar
  trigger is reachable.

Playwright browser binaries are **not currently installed** on the development
machine (the `ms-playwright` cache is empty), so this requires a one-time
`npx playwright install chromium` of roughly 140MB locally, and an install step
in CI.

### 6. CI wiring

`.github/workflows/ci.yml`, frontend job, after the existing typecheck and build
steps: `npm test`, then `npx playwright install --with-deps chromium`, then
`npx playwright test`. The job count stays at two.

The trailing comment block explaining why there is no `npm test` step is deleted
— it documents a condition this phase removes, and a comment that outlives its
condition is worse than no comment.

## Order of work

The sequence is not arbitrary; each step exists to keep the next step's evidence
interpretable.

1. **devDep CVE bumps** (`vitest`, `vite`, `postcss`), verified by `tsc -b` and
   `npm run build`. First, because bumping `vite` can change chunk output — and
   step 3's entire evidence is a chunk-size comparison.
2. **Harness, mapper tests, error boundary.**
3. **Code splitting**, with the before/after chunk manifest captured.
4. **Playwright config and both specs.**
5. **CI wiring.**
6. **Full verification**: `pytest`, `tsc -b`, `npm run build`, `npm test`,
   `npx playwright test`.

## Risks

| Risk | Mitigation |
|---|---|
| `jsdom` is pinned at 20.0.3 (2022) against vitest 3.2.4 | Bump it if the harness fails to start. It is a devDependency with no CVE implication. |
| Playwright browsers absent locally; CI needs an install step | One-time ~140MB local download; roughly 30s added per CI run. |
| Mocks drift from the real backend contract | Accepted by decision. Fixtures derive from the real shapes in `api.ts` and `response-mapper.ts`; the contract itself stays covered by pytest. |
| `vite` bump shifts chunk output | Bump lands before the splitting measurement, so the comparison is against the new baseline. |
| Vitest collecting Playwright specs, or the reverse | `include` is narrowed to `src/**/*.test.*`; Playwright's `testDir` is `e2e/`. Distinct suffixes (`.test.` vs `.spec.`) as well as distinct directories. |

## Success criteria

- `npm test` runs a non-empty suite and passes.
- `npx playwright test` passes at desktop, 768px, and 375px.
- No route overflows horizontally at either mobile width.
- The `vite build` entry chunk is measurably smaller than at `bf8b084`.
- A throwing page renders the boundary fallback with the sidebar still usable.
- `pytest` stays at 288 passed / 0 failed; `tsc -b` and the detector gate stay at
  exit 0.
- CI is green on the branch before it merges.
