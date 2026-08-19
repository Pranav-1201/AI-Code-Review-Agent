# FLOW — how execution actually travels

Bugs live in the gaps between files. This traces the real call path with real
line numbers, so the gaps are visible.

Line numbers are accurate as of commit `06de9fc`. If they drift, the shape still
holds — re-grep the function name rather than trusting the number.

---

## Path 1 — a scan, end to end

This is the path that matters. Almost every bug in this project is somewhere on
it.

### Stage 0 — request arrives

`main.py:361` `@app.post("/scan")` → `start_scan(payload, request)`

Before this runs, two middlewares have already executed. Order matters and is
deliberate: CORS is registered **after** auth so it sits *outside* it, which is
why a 401 still comes back with CORS headers and the browser can show
"unauthorized" instead of an opaque network error.

```
request
  └─ CORSMiddleware              main.py:136   (outermost)
      └─ require_api_key         main.py:100   OPTIONS is exempt by design
          └─ route handler
```

### Stage 1 — the trust boundary

Inside `start_scan`, in this order — and the order is the point:

1. `api_guard.check_rate_limit("scan", client_identity(request))` — **rate limit
   first**, so a flood of malformed URLs is shed as cheaply as valid ones.
   Returns a retry-after → `429`.
2. `api_guard.validate_repo_url(payload.repo_path)` — host allowlist, private-IP
   rejection, length cap. Raises `RepoUrlError` → `422`.
3. `create_scan(repo_url)` → a `scan_id`
4. `run_scan_task.delay(scan_id, repo_url, explanation_depth)`

`.delay()` goes to Celery. **With no broker configured it runs eagerly, in
process** — same code path, no queue. The task defers to
`main.run_scan_pipeline`, which is what makes a monkeypatch of that name work in
tests.

Returns `{"scan_id": ...}` immediately. Everything after this is asynchronous
from the browser's point of view.

### Stage 2 — the pipeline

`main.py:237` `run_scan_pipeline` → `main.py:243` `_run_scan_pipeline`

```
_run_scan_pipeline(scan_id, repo_url, explanation_depth)
│
├─ repo_dir = CLONE_CACHE / md5(repo_url)
│
├─ disk_guard sweep                      ← OUTSIDE the main try block, on purpose
│    Best-effort. An exception here would escape before complete_scan() runs and
│    strand the scan in a non-terminal state with no error shown to the user.
│    Eviction is housekeeping, not part of the scan's contract.
│    `keep` is this scan's own key, so a sweep can never delete the clone this
│    run is about to reuse.
│
├─ incremental.load_prior(repo_url)
│   ├─ HIT  → update_scan(..., "cloning", 5)   refresh cached clone
│   │         since_sha, prior_files ← prior
│   └─ MISS → update_scan(..., "cloning", 5)   full clone WITH history
│             (deliberately not --depth 1, so future re-scans can diff)
│
├─ update_scan(..., "analyzing", 15)
├─ result = run_pipeline(repo_dir, scan_id, since_sha, prior_files, depth)
│
├─ files_data = result.pop("_files_data")     internal, never persisted
├─ update_scan(..., "finalizing", 90)
├─ incremental.head_sha(repo_dir) → save prior for next time
└─ complete_scan(scan_id, result)
```

Failure path: the `except` calls `complete_scan(scan_id, {"error": str(e)})`.
Every failure still reaches a terminal state — which is exactly why the disk
sweep is kept outside the try.

### Stage 3 — the analysis itself

`main.py:167` `run_pipeline(repo_path, ...)`

```
run_pipeline
│
├─ files = analyze_repository(repo_path, since_sha, prior_files)
│     backend/app/services/repo_analyzer.py
│     Walks the tree, parses each file, returns per-file dicts.
│     INCREMENTAL: with since_sha + prior_files it re-analyzes only
│     git-diff-changed files and reuses the rest.
│     Per file this produces: functions, imports, dead_code, code_smells,
│     complexity_metrics, cyclomatic_complexity, documentation_coverage,
│     file_type (production/test), file_role, cohesion.
│
├─ settings = load_settings(); max_files (default 2000)
│     files = files[:max_files]        ← large repos are TRUNCATED here
│
├─ dependency_graph = build_dependency_graph(files)
├─ call_graph       = build_call_graph(files)
│
└─ engine = RepositoryReviewEngine()
   result = engine.review_repository(repo_path, files, explanation_depth)
        Assembles summary, insights, per-file entries, dependencies,
        duplicates and the graph into the final report JSON.
```

**Where security findings are produced:** inside the per-file analysis, via
`backend/app/services/security_analyzer.py`. That file is where Phase G works.
The AST visitors that matter:

- `visit_Call` — dangerous functions, command injection, deserialization
- `visit_BinOp` — SQL injection via string concatenation
- `visit_JoinedStr` — SQL injection via f-string ← **S2 lives here**
- `visit_Attribute` — weak crypto (`hashlib.md5` / `sha1`), with a
  context classifier that correctly suppresses SHA-1 under HMAC

### Stage 4 — the browser gets the result

Two routes, and the frontend uses both:

- `GET /scan/{id}/stream` — SSE progress. **EventSource cannot set headers**, so
  this one route accepts `?api_key=` as a fallback. Scoped to this route only,
  because query strings land in proxy logs and browser history.
- `GET /scan/{id}` — polling fallback when SSE is unavailable.

---

## Path 2 — the frontend calling the backend

Every call funnels through one module. This is deliberate: settings pages used
to hold raw `fetch("http://localhost:8000/...")` calls, which were invisible to
the API-base and API-key handling.

```
frontend/src/lib/api.ts
├─ API_BASE  = VITE_API_BASE ?? "http://localhost:8000"   ← BUILD-time inline
├─ API_KEY   = VITE_API_KEY                               ← BUILD-time inline
├─ apiHeaders(extra)  → adds X-API-Key when present
└─ startScan / getScan / getScans / getSettings / saveSettings / resetSettings
```

**`VITE_*` values are inlined at build time, not read at runtime.** Changing one
requires a rebuild, not a restart. This is the single most common source of
"I changed the env var and nothing happened".

### The origin trap that broke the app (fixed in `03dccba`)

```
Vite dev server  :8080  ──►  backend  :8000
                              └─ CORS allowlist: localhost:8080, :5173
                                                 127.0.0.1:8080, :5173
```

If Vite is not on 8080, the browser's `Origin` falls outside that allowlist and
**every preflight returns 400 `Disallowed CORS origin`** — while the uvicorn log
shows only a bare `OPTIONS /scan 400`, because Starlette puts the reason in the
response body where only the browser console sees it.

`strictPort: true` now prevents the drift. Two tests pin the Vite port to the
backend allowlist, because they are in different languages with nothing else
connecting them.

---

## Path 3 — layout and the sidebar (BUG-001 territory)

```
DashboardLayout.tsx
└─ SidebarProvider                      ui/sidebar.tsx  (sets --sidebar-width)
   ├─ AppSidebar                        <Sidebar collapsible="icon">
   │  └─ desktop root: "hidden md:block"        ui/sidebar.tsx:182
   │     ├─ gap div    w-[--sidebar-width]      :189
   │     └─ fixed div  z-10 ... md:flex         :201
   └─ div.flex-1
      └─ header  sticky top-0 z-10
         └─ SidebarTrigger → toggleSidebar()    :230
```

`useIsMobile()` (`hooks/use-mobile.tsx`) hardcodes `MOBILE_BREAKPOINT = 768`.
Tailwind's `md` is also 768 — the `screens` override in `tailwind.config.ts` is
scoped to `container` and does not change the breakpoints. Below 768 the sidebar
is a Sheet; at or above it is the fixed desktop sidebar.

This path is where BUG-001 lives and has not yet been root-caused. See
`docs/bugs/BUG-001-sidebar-split-view.md` for what has already been ruled out.
