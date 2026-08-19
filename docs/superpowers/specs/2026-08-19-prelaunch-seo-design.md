# Pre-launch / SEO phase — design

**Status:** approved 2026-08-19
**Predecessor:** Phase F (single-origin VPS deploy), `main` = `f341461`
**Source of scope:** `Desktop\Claude Prompts\Website Pre-Launch Guide.docx`, filtered
against the actual tree. Most of that guide targets a marketing website for a
local business and does not apply; see "Explicitly out of scope" below.

---

## 1. Problem

The application is meant to be **public and indexed**. Five things are wrong or
missing at the HTTP and document level. None of them are application bugs — the
app works. They are all launch-surface defects.

| # | Defect | Evidence |
|---|--------|----------|
| 1 | Every unknown URL returns **HTTP 200** | `Caddyfile` `try_files {path} /index.html` |
| 2 | No favicon of any kind | `frontend/public/` holds only `placeholder.svg`, `robots.txt`; `index.html` has no icon link |
| 3 | A scaffold `TODO` comment ships in production HTML | `frontend/index.html:8` |
| 4 | `twitter:card` is `summary_large_image` with **no `og:image`** | `frontend/index.html:12` — shares render a blank card |
| 5 | No security response headers | `Caddyfile` sets none |

Plus the requested SEO surface, absent entirely: `sitemap.xml`, canonical
links, and per-page titles/descriptions. All 15 routes currently share the one
static `<title>AI Code Review</title>`.

### 1.1 Defect 1 is narrower than it looks, and that matters

`App.tsx` already has `<Route path="*" element={<NotFound />} />`, and
`NotFound` already renders. A visitor to `/nonsense` sees a correct 404 page.
**Only the status code is wrong.** Crawlers read the status, not the page, so
every mistyped URL is currently an indexable duplicate of the shell.

This changes the fix: we are not building a 404 experience, we are correcting a
status code while preserving the experience that exists.

---

## 2. Core design decision: one route table, four consumers

Four separate pieces of this phase need the same list of 15 paths:

1. **Caddy** — which paths get the SPA shell, and which 404
2. **The head manager** — per-path `<title>` and `<meta name="description">`
3. **The sitemap generator** — one `<url><loc>` per indexable path
4. **The drift test** — proving 1 and 2 have not diverged

Today that list exists once, as JSX inside `App.tsx:71-85`. Copying it into a
Caddyfile and a sitemap generator would create three lists that must be kept in
sync by hand — the exact rot the source guide warns about.

**Decision:** extract `frontend/src/lib/routes.ts` as the single source of
truth. `App.tsx` renders from it; the head manager reads from it; the Vite
plugin emits the sitemap from it; the drift test compares the Caddyfile against
it. One list to change, one test proving the one place Caddy still agrees.

### 2.1 Hard constraint on `routes.ts`

`vite.config.ts` must import `routes.ts` at build time, in Node, to generate the
sitemap. Therefore **`routes.ts` must contain no React import, no JSX, and no
`import.meta.env` access** — plain data and types only. The lazy `import()`
calls stay in `App.tsx`, keyed by path.

Violating this turns a config import into a build failure, so the drift test
also asserts the file's import list is empty.

### 2.2 Shape

```ts
export type RouteMeta = {
  /** URL path, exactly as Caddy and React Router see it. */
  path: string;
  /** Per-page <title>. The site name is appended by the head manager. */
  title: string;
  /** Per-page <meta name="description">. */
  description: string;
  /** False keeps the path out of sitemap.xml and adds noindex. */
  indexable: boolean;
};

export const ROUTES: readonly RouteMeta[] = [ /* 15 entries */ ];
export const SITE_NAME = "AI Code Review";
```

`/settings` is the one route with `indexable: false` — it is a user preferences
screen with nothing to rank for, and listing it invites crawl budget waste.
Every other route is indexable, including `/results` and `/history`, which are
empty without a scan but are legitimate app surfaces.

---

## 3. The 404 fix

### 3.1 Caddy structure

Replace the single `handle` block with three:

```
@spa path / /results /overview /file-analysis /security /quality \
           /dependencies /ai-suggestions /health /history /issues \
           /duplicates /visualizations /export /settings

handle @spa {
    root * /srv
    rewrite * /index.html
    file_server
}

handle {
    root * /srv
    file_server
}

handle_errors {
    root * /srv
    rewrite * /404.html
    file_server {
        status {err.status_code}
    }
}
```

Reading it in order:

- **`@spa`** matches the 15 known client routes. `path` with multiple arguments
  is a logical OR, and matches are exact (no implicit prefix), which is what we
  want — `/security` is a route, `/security/anything` is not.
- **First `handle`** serves the shell for those paths. `rewrite` (not
  `try_files`) because we already know the answer is `index.html`; `try_files`
  would re-introduce the fallback we are removing.
- **Second `handle`** is everything else. `file_server` serves real files —
  `/assets/index-abc123.js`, `/favicon.svg`, `/robots.txt`, `/sitemap.xml` —
  with 200, and returns a genuine 404 for anything with no file behind it.
  This is what fixes `/favicon.ico` currently returning the app shell.
- **`handle_errors`** turns that bare 404 back into the app's own 404 page.
  `status {err.status_code}` is the load-bearing part: without it `file_server`
  would serve `404.html` with **200**, reproducing the exact bug we are fixing
  one layer down.

### 3.2 Where `404.html` comes from

Vite emits no `404.html`. A `closeBundle` hook in the Vite plugin copies
`dist/index.html` → `dist/404.html` after the build.

Consequence, and it is the desired one: the 404 page **is** the SPA. It boots,
React Router matches `*`, and renders the existing `NotFound` component. The
user sees exactly what they see today; the status line now says 404.

### 3.3 The drift test

`frontend/src/lib/routes.test.ts` reads `../Caddyfile` from disk, extracts the
`@spa path ...` argument list (joining `\` continuations), and asserts it equals
the set of `ROUTES[].path`. Adding a route to `routes.ts` without touching the
Caddyfile fails the test with both lists printed.

This is the whole reason a route list is tolerable in a config file.

---

## 4. Head manager

### 4.1 No new dependency

`react-helmet-async` exists to solve head management **during server-side
rendering**, where you must collect tags out-of-band and serialise them into an
HTML string. This app is a static SPA served by a file server. There is no
render pass to collect from.

**Decision:** a `useDocumentHead` hook (~40 lines) that writes
`document.title` and upserts `<meta>` / `<link rel="canonical">` in an effect.
No dependency, no provider, nothing to keep in sync with React versions.

### 4.2 Placement

A single `<RouteHead />` rendered once inside `<BrowserRouter>`, which reads
`useLocation()` and looks the path up in `ROUTES`. **Not** 15 per-page calls —
that would be 15 files to touch and 15 chances to forget one, and the metadata
already lives centrally.

Unknown paths (the `*` route) get the 404 title and `noindex`.

### 4.3 What it sets

Per navigation:

- `document.title` — `"{route.title} · {SITE_NAME}"`, except `/` which is
  `SITE_NAME` alone (a home page titled "Scan a repository · AI Code Review"
  reads worse in a SERP than the product name)
- `<meta name="description">`
- `<meta property="og:title">`, `og:description`, `og:url`
- `<link rel="canonical">` — **only when `VITE_SITE_URL` is set**
- `<meta name="robots" content="noindex">` — only when `indexable` is false

Tags are upserted by selector and never removed, so a route that omits one
inherits the previous value rather than flickering. Every route in `ROUTES`
supplies both title and description, so this only affects the `*` case.

---

## 5. `VITE_SITE_URL` — the domain question

There is no domain yet. Phase F already answered the equivalent question for
TLS with `SITE_ADDRESS`, and this follows it.

`VITE_SITE_URL` (e.g. `https://example.com`) is **empty by default**. When empty:

- no `sitemap.xml` is emitted
- no `Sitemap:` line is added to `robots.txt`
- no `<link rel="canonical">` is rendered
- `og:url` is omitted

Rationale: a canonical pointing at a placeholder origin is worse than no
canonical — it actively tells crawlers the wrong thing. Absent is honest.

Setting the variable at build time turns all four on with no code change. It is
a build arg on `frontend/Dockerfile` alongside `VITE_API_BASE`, and unlike
`VITE_API_KEY` it is safe to bake into a published image because it is public
information by definition.

---

## 6. Sitemap and robots

A Vite plugin, `frontend/vite-plugin-seo.ts`, doing three things in
`closeBundle`:

1. Copy `dist/index.html` → `dist/404.html` (always)
2. Write `dist/sitemap.xml` from `ROUTES.filter(r => r.indexable)` (only when
   `VITE_SITE_URL` is set)
3. Append `Sitemap: {VITE_SITE_URL}/sitemap.xml` to `dist/robots.txt` (same
   condition)

`robots.txt` keeps its current `Allow: /` content for every agent — the site is
public, so the existing file is already correct and only gains the sitemap
pointer.

No `<lastmod>`. It would have to be either a build timestamp (which lies: the
page did not change) or hand-maintained (which rots). Google ignores
`<changefreq>` and `<priority>` outright, so both are omitted too.

---

## 7. Security headers

Added to the Caddyfile site block, applying to every response.

```
header {
    Strict-Transport-Security "max-age=31536000"
    X-Content-Type-Options "nosniff"
    Referrer-Policy "strict-origin-when-cross-origin"
    X-Frame-Options "DENY"
    Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data: blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'"
    -Server
}
```

Per-directive justification, because a CSP copied without understanding is a CSP
that gets disabled at the first breakage:

- **`style-src` needs `'unsafe-inline'`.** Radix UI and vaul set inline `style`
  attributes for positioning. Inline style *attributes* fall back to `style-src`
  when `style-src-attr` is absent. Without this, every popover, tooltip, and
  drawer in the app breaks. This is a real weakening and it is unavoidable
  short of replacing the component library.
- **`fonts.googleapis.com` / `fonts.gstatic.com`** are required by
  `src/index.css:1`, which loads Inter and JetBrains Mono from Google Fonts.
- **`script-src 'self'` with no `'unsafe-inline'`** — this is the directive that
  actually stops XSS, and it must not be weakened. Vite's build emits external
  module scripts. *If* the build emits an inline module-preload polyfill, this
  breaks the app, which is precisely why CI must load the page rather than only
  assert the header exists. See §9.
- **`connect-src 'self'`** covers both the API and the SSE stream, because the
  whole point of Phase F's single origin is that they are same-origin.
- **`img-src` includes `data:` and `blob:`** for recharts and the dependency
  graph renderer.
- **HSTS without `includeSubDomains` or `preload`.** Both are effectively
  one-way doors on a domain that does not exist yet: `includeSubDomains` breaks
  any future plain-HTTP subdomain, and `preload` is famously hard to reverse.
  `max-age` alone is the reversible choice; `DEPLOYMENT.md` documents how to
  harden it once a domain is settled and stable.
- **`X-Frame-Options: DENY` alongside `frame-ancestors 'none'`** is deliberate
  redundancy for old browsers that do not implement CSP Level 2.
- **`-Server`** removes Caddy's version banner.

HSTS is emitted unconditionally. Browsers ignore `Strict-Transport-Security` on
plain-HTTP responses per RFC 6797 §8.1, so this is inert on the `:80` default
and correct the moment a hostname is set.

---

## 8. Images

### 8.1 What is needed

| File | Size | Purpose |
|------|------|---------|
| `favicon.svg` | vector | modern browsers |
| `favicon.ico` | 32×32 | legacy, and the bare `/favicon.ico` request browsers make anyway |
| `apple-touch-icon.png` | 180×180 | iOS home screen |
| `og-image.png` | 1200×630 | the blank-share-card fix |

### 8.2 Generated, not hand-drawn

`scripts/generate-brand-assets.py` produces all four from the palette already in
`src/index.css` (`--background: 220 20% 7%`, `--primary: 142 72% 50%`). Pillow
12 is present on the dev machine.

The script is committed and the outputs are committed. **The build gains no
dependency** — Pillow is never installed by `frontend/Dockerfile`, CI, or the
production image. This is the Phase E `httpx` and Phase F `pyyaml` lesson
applied forward: a tool that only runs on a developer's machine must not become
something the build imports.

Regenerating is a manual step, documented in the script's header.

### 8.3 Design

Deliberately minimal, because this is a launch-surface fix and not the design
phase: the product wordmark on the app's own near-black background, with the
primary green as the accent. `og-image.png` carries the name and the one-line
description already in `index.html`.

---

## 9. Verification

### 9.1 Local

- `vitest` — the drift test, plus a `useDocumentHead` test asserting title and
  canonical behaviour with `VITE_SITE_URL` set and unset
- `tsc -b` — 0 errors
- `npm run build` — must emit `dist/404.html`, and `dist/sitemap.xml` only when
  `VITE_SITE_URL` is set

### 9.2 CI (`deploy-stack`)

The `deploy-stack` job added in Phase F already builds both images and boots the
stack. It gains assertions, each mapping to one defect above:

1. `GET /` → **200**
2. `GET /nonsense` → **404** (defect 1)
3. `GET /nonsense` body contains `id="root"` — proving `handle_errors` served
   the app shell and not Caddy's plain-text `404 page not found`. The body
   cannot be checked for the *rendered* 404 text: `NotFound.tsx` renders
   client-side, and `404.html` is a byte-copy of `index.html`, so what curl
   receives is the shell either way. Presence of the mount point is the only
   thing that actually distinguishes the two outcomes over HTTP.
4. `GET /history` → **200** (the client-side deep link still works — this is the
   regression the `@spa` list exists to prevent)
5. `GET /favicon.svg` → **200** (defect 2)
6. `GET /` headers contain `Content-Security-Policy`, `X-Content-Type-Options`,
   `Referrer-Policy` (defect 5)
7. `GET /assets/*.js` → **200** — the asset path must survive the routing change
8. `caddy validate` still passes

Assertion 3 is the one that catches the `status {err.status_code}` mistake, and
assertion 7 is the one that catches an over-eager `@spa` matcher.

### 9.3 What CI does not prove

CSP is asserted as *present*, not as *non-breaking* — a header check cannot tell
you a chart failed to render. The Playwright suite (15 tests, added in Phase D)
runs against the dev server, which does not go through Caddy and therefore has
no CSP. **Closing that gap is out of scope for this phase and is stated as a
known limitation in `DEPLOYMENT.md`**, alongside the Phase F limitations (TLS
issuance, real DNS, load).

The honest summary: if CSP breaks a Radix popover, this phase's tests will not
tell you. The `'unsafe-inline'` in `style-src` is what makes that unlikely, and
it is why that directive is weakened deliberately rather than reluctantly.

---

## 10. Google Search Console

Verification requires a real domain, so it cannot be completed now. What ships
is the mechanism: `VITE_SEARCH_CONSOLE_TOKEN`, empty by default, rendered as
`<meta name="google-site-verification">` by the head manager when set. The
DNS-TXT alternative is documented in `DEPLOYMENT.md` as the better option once a
domain exists, since it survives a rebuild.

---

## 11. Explicitly out of scope

**From the source guide, not applicable to a self-hosted developer tool:**
tap-to-call, opening hours, maps and directions, local business schema, team
photo, case studies, before/after gallery, blog posts, testimonials, sticky
mobile CTA, thank-you page.

**Deferred deliberately:**

- **Part II of the guide (AI design tells).** Inter, purple accent on near-black,
  `--radius: 0.5rem`, Lucide icons across 39 files. Real, and a design phase, not
  a pre-deployment one.
- **CSP verified against a real browser.** §9.3.
- **`JSON-LD` structured data.** `SoftwareApplication` schema is plausible here,
  but it earns nothing until the site has a domain and impressions to measure
  against.

---

## 12. Files

**Create:**

- `frontend/src/lib/routes.ts` — the route table
- `frontend/src/lib/routes.test.ts` — Caddyfile drift test
- `frontend/src/hooks/useDocumentHead.ts` — head manager
- `frontend/src/hooks/useDocumentHead.test.ts`
- `frontend/src/components/RouteHead.tsx`
- `frontend/vite-plugin-seo.ts` — 404.html, sitemap.xml, robots.txt
- `scripts/generate-brand-assets.py`
- `frontend/public/favicon.svg`, `favicon.ico`, `apple-touch-icon.png`,
  `og-image.png`

**Modify:**

- `Caddyfile` — `@spa` matcher, `handle_errors`, `header` block
- `frontend/src/App.tsx` — render routes from `ROUTES`, mount `<RouteHead />`
- `frontend/index.html` — drop the `TODO` (defect 3), add icon links and
  `og:image` (defects 2, 4)
- `frontend/vite.config.ts` — register the plugin
- `frontend/Dockerfile` — `VITE_SITE_URL`, `VITE_SEARCH_CONSOLE_TOKEN` build args
- `.github/workflows/ci.yml` — the eight `deploy-stack` assertions
- `.github/workflows/release.yml` — pass `VITE_SITE_URL` to the web image build
- `.env.example`, `DEPLOYMENT.md` — the new variables and the known limitation
