# Pre-launch / SEO Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to
> implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Correct the five launch-surface defects and add the SEO surface, with
the 15-route list held in exactly one place and a test proving it.

**Architecture:** `frontend/src/lib/routes.ts` is the single source of truth.
`App.tsx`, the head manager, a Vite plugin, and a drift test all read it. Caddy
holds a mirror of the path list, and the drift test is what keeps the mirror
honest.

**Tech Stack:** React 18 + react-router-dom 6, Vite 5, vitest 3, Caddy 2,
Pillow 12 (developer machine only — never a build dependency).

**Spec:** `docs/superpowers/specs/2026-08-19-prelaunch-seo-design.md`

## Global Constraints

- `frontend/src/lib/routes.ts` imports **nothing**. `vite.config.ts` imports it
  in Node at build time; a React or `import.meta.env` import breaks the build.
- Pillow is **not** added to any requirements file, `frontend/Dockerfile`, or CI.
  Generated images are committed as binaries; the generator is run by hand.
- `VITE_SITE_URL` defaults to **empty**. Empty means no canonical, no
  `sitemap.xml`, no `Sitemap:` line, no `og:url` — never a placeholder origin.
- `VITE_API_KEY` continues to be **absent** from `release.yml`. Do not add it.
- HSTS ships as `max-age=31536000` only — no `includeSubDomains`, no `preload`.
- No AI/assistant attribution in any commit message (`CLAUDE.md`).
- Branch: `prelaunch/seo-404-headers`. Never commit to `main` directly.

---

### Task 1: The route table

**Files:**
- Create: `frontend/src/lib/routes.ts`
- Create: `frontend/src/lib/routes.test.ts`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Produces: `ROUTES: readonly RouteMeta[]`, `SITE_NAME: string`,
  `routeFor(path: string): RouteMeta | undefined`, and the `RouteMeta` type
  (`path`, `title`, `description`, `indexable`) — consumed by Tasks 2, 3, 4.

- [ ] **Step 1:** Write `routes.ts` with all 15 entries, paths copied verbatim
      from `App.tsx:71-85`. Titles and descriptions are per-page and specific —
      no "Page for X" filler. `/settings` gets `indexable: false`; the other 14
      are `true`.
- [ ] **Step 2:** Write the failing drift test: read `../Caddyfile`, extract the
      `@spa path` argument list joining `\` continuations, assert set-equality
      with `ROUTES.map(r => r.path)`. Second test: assert `routes.ts` source
      contains no `import` statement.
- [ ] **Step 3:** Run `npx vitest run src/lib/routes.test.ts` — expect FAIL
      (no `@spa` in the Caddyfile yet). This failure is the point: it proves the
      test reads the real file rather than passing vacuously.
- [ ] **Step 4:** Rewrite `App.tsx` `<Routes>` to render from `ROUTES` via a
      path→lazy-component map. Keep `RepositoryScanner` eager and every other
      page lazy — the 387 kB entry chunk from Phase D must not regress. Keep the
      `*` → `NotFound` route.
- [ ] **Step 5:** `npx tsc -b` → 0 errors; `npx vitest run` → existing 22 pass.
- [ ] **Step 6:** Commit.

---

### Task 2: Caddy — real 404, and the headers

**Files:**
- Modify: `Caddyfile`

**Interfaces:**
- Consumes: the path list from Task 1 (mirrored, not imported).

- [ ] **Step 1:** Replace the single `handle` with `@spa` + `handle @spa` +
      bare `handle` + `handle_errors`, exactly as spec §3.1. Keep every existing
      comment on `handle_path /api/*` — the `header_up` and `flush_interval`
      rationale is still load-bearing.
- [ ] **Step 2:** Add the `header` block from spec §7, with the per-directive
      comments. `-Server` included.
- [ ] **Step 3:** Run `npx vitest run src/lib/routes.test.ts` from `frontend/` —
      now expect PASS. Task 1 step 3 failed here; this is the same test passing
      for a real reason.
- [ ] **Step 4:** Commit. The message must record *why* `status
      {err.status_code}` exists, because it is invisible and its absence
      reproduces the exact bug being fixed.

---

### Task 3: Head manager

**Files:**
- Create: `frontend/src/hooks/useDocumentHead.ts`
- Create: `frontend/src/hooks/useDocumentHead.test.ts`
- Create: `frontend/src/components/RouteHead.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `ROUTES`, `SITE_NAME`, `routeFor` (Task 1).
- Produces: `useDocumentHead(meta: DocumentHead): void`, `<RouteHead />`.

- [ ] **Step 1:** Write the failing tests: title is `SITE_NAME` alone on `/`
      and `"{title} · {SITE_NAME}"` elsewhere; `<link rel="canonical">` is
      absent when `VITE_SITE_URL` is empty and present when set; `noindex` is
      emitted only for `indexable: false`; an unknown path gets the 404 title
      and `noindex`.
- [ ] **Step 2:** Run them — expect FAIL (module not found).
- [ ] **Step 3:** Implement `useDocumentHead` — upsert by selector, never
      remove. Implement `RouteHead` using `useLocation()` + `routeFor`. Emit
      `<meta name="google-site-verification">` when
      `VITE_SEARCH_CONSOLE_TOKEN` is set.
- [ ] **Step 4:** Mount `<RouteHead />` once inside `<BrowserRouter>`, above
      `<Routes>`.
- [ ] **Step 5:** Tests PASS; `npx tsc -b` → 0.
- [ ] **Step 6:** Commit.

---

### Task 4: Vite plugin — 404.html, sitemap, robots

**Files:**
- Create: `frontend/vite-plugin-seo.ts`
- Modify: `frontend/vite.config.ts`

**Interfaces:**
- Consumes: `ROUTES` (Task 1) — imported in Node, which is why Task 1's
  no-import rule exists.

- [ ] **Step 1:** Write the plugin: `closeBundle` copies `dist/index.html` →
      `dist/404.html` unconditionally; writes `dist/sitemap.xml` and appends the
      `Sitemap:` line to `dist/robots.txt` only when `VITE_SITE_URL` is set.
      No `<lastmod>`, `<changefreq>`, or `<priority>` (spec §6).
- [ ] **Step 2:** Register it in `vite.config.ts` after `react()`.
- [ ] **Step 3:** `npm run build` with `VITE_SITE_URL` unset. Verify
      `dist/404.html` exists, `dist/sitemap.xml` does **not**, and
      `dist/robots.txt` has no `Sitemap:` line. Record the entry chunk size and
      confirm it has not regressed past 387 kB.
- [ ] **Step 4:** `VITE_SITE_URL=https://example.com npm run build`. Verify
      `sitemap.xml` exists with **14** `<loc>` entries (15 routes minus
      `/settings`) and `robots.txt` gained the line.
- [ ] **Step 5:** Commit.

---

### Task 5: Brand assets and `index.html`

**Files:**
- Create: `scripts/generate-brand-assets.py`
- Create: `frontend/public/favicon.svg`, `favicon.ico`,
  `apple-touch-icon.png`, `og-image.png`
- Modify: `frontend/index.html`

- [ ] **Step 1:** Write the generator. Palette read from the spec (§8.2), header
      comment stating it is run by hand and that Pillow must never enter the
      build.
- [ ] **Step 2:** Run it. Verify the four files exist with the right dimensions.
- [ ] **Step 3:** Edit `index.html`: delete the `TODO` comment (defect 3); add
      `<link rel="icon" href="/favicon.svg" type="image/svg+xml">`,
      `<link rel="icon" href="/favicon.ico" sizes="32x32">`,
      `<link rel="apple-touch-icon" href="/apple-touch-icon.png">`; add
      `<meta property="og:image" content="/og-image.png">` and
      `<meta name="twitter:image" content="/og-image.png">` (defects 2, 4).
- [ ] **Step 4:** `grep -c TODO frontend/index.html` → 0. `npm run build`, then
      confirm all four files are present in `dist/`.
- [ ] **Step 5:** Commit.

---

### Task 6: CI assertions, build args, docs

**Files:**
- Modify: `.github/workflows/ci.yml`, `.github/workflows/release.yml`
- Modify: `frontend/Dockerfile`, `.env.example`, `DEPLOYMENT.md`

- [ ] **Step 1:** Add `ARG VITE_SITE_URL=` / `ARG VITE_SEARCH_CONSOLE_TOKEN=`
      to `frontend/Dockerfile`, following the existing `VITE_API_BASE` pattern.
      Comment why `VITE_SITE_URL` is safe to bake into a published image while
      `VITE_API_KEY` is not.
- [ ] **Step 2:** Add the eight `deploy-stack` assertions from spec §9.2. Each
      failure message must name the defect it guards, so a red CI run is
      self-explaining.
- [ ] **Step 3:** Pass `VITE_SITE_URL` through in `release.yml` (empty unless
      set as a repo variable). Do **not** add `VITE_API_KEY`.
- [ ] **Step 4:** Document the new variables in `.env.example` and the new
      section in `DEPLOYMENT.md`, including the §9.3 limitation stated plainly:
      CSP is asserted present, not proven non-breaking.
- [ ] **Step 5:** Full local gate — `pytest` (324), detector gate, `tsc -b`,
      `vitest`, `npm run build`. Then push and confirm all four CI jobs green.
- [ ] **Step 6:** Commit, then finish the branch via
      superpowers:finishing-a-development-branch.
