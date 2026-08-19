# ARCHITECTURE — the shape of the system

A map, not implementation detail. The point is that a session can reason about
impact before writing a line, instead of re-deriving the terrain every time.

---

## What it is

A repository health analyzer. Give it a public git URL; it clones the repo, runs
a deterministic AST analysis over the source, and returns a structured report:
per-file scores, complexity, security candidates, dependencies, duplication, a
dependency graph and a health narrative.

**Every finding is deterministic.** The LLM layer is off by default and, when
on, only paraphrases findings that already exist. It never detects anything.

---

## Stack

| Layer | Technology |
|---|---|
| API | FastAPI + uvicorn (`main.py`) |
| Queue | Celery — **eager in-process unless `CELERY_BROKER_URL` is set** |
| Store | SQLite with WAL (`backend/database/`) |
| Analysis | Pure Python stdlib `ast`; iterative Tarjan SCC for call graphs |
| LLM | Anthropic, gated behind `ENABLE_ANTHROPIC` + a key, paraphrase-only |
| Frontend | React 18 + TypeScript, Vite 5.4.21, Tailwind, shadcn/ui, Recharts |
| Edge | Caddy, single origin, auto-TLS |
| Images | Docker Compose, sha-tagged images on GHCR |

---

## Module map

```
main.py                    API surface, run_pipeline, run_scan_pipeline
│
├── backend/app/
│   ├── api_guard.py       THE HTTP trust boundary, all of it, one file
│   ├── config.py          settings
│   ├── disk_guard.py      clone size ceilings + LRU eviction
│   ├── observability.py   structured logging, Sentry
│   │
│   ├── analysis/          PURE — no I/O, no network, no DB
│   │   ├── ast_parser.py            per-file parse and metrics
│   │   ├── symbol_table.py          name resolution
│   │   ├── call_graph.py            interprocedural graph (Tarjan SCC)
│   │   ├── taint_analyzer.py        source→sink, intra + param-IN interproc
│   │   ├── dependency_analyzer.py   manifests, versions, OSV lookup
│   │   ├── dependency_graph.py      import graph
│   │   ├── complexity_analyzer.py   cyclomatic, nesting, time complexity
│   │   ├── dead_code_detector.py    unused imports and functions
│   │   ├── duplicate_detector.py    near-duplicate blocks
│   │   ├── cohesion_analyzer.py     file size and cohesion flags
│   │   ├── architecture_analyzer.py layering checks
│   │   ├── code_smell_detector.py
│   │   ├── framework_detector.py    import-signature fingerprinting
│   │   ├── heuristic_refactor_engine.py   AST transforms, NO LLM
│   │   ├── patch_generator.py
│   │   └── js_structure.py          JS/TS structural pass
│   │
│   └── services/          ORCHESTRATION — I/O lives here
│       ├── repo_analyzer.py         analyze_repository: walk + per-file
│       ├── security_analyzer.py     the 11 finding types  ← Phase G works here
│       ├── repository_review_engine.py  assembles the final report
│       ├── quality_scorer.py        scores and health
│       ├── explanation_engine.py    prose; deterministic or LLM
│       ├── llm_service.py           Anthropic client, gated
│       ├── scan_manager.py          scan lifecycle + progress
│       ├── cache_manager.py         per-file analysis cache
│       ├── incremental.py           prior store, re-scan diffing
│       ├── github_service.py        repo metadata
│       ├── report_generator.py      export
│       ├── celery_app.py            queue config (reads env at IMPORT time)
│       └── tasks.py                 the Celery task
│
├── backend/benchmark/     corpus + thresholds — the accuracy gate
└── frontend/src/
    ├── lib/routes.ts      single route table — imports NOTHING
    ├── lib/api.ts         every backend call goes through here
    ├── components/        DashboardLayout, AppSidebar, ui/ (shadcn)
    └── pages/             18 pages, lazily loaded
```

**The `analysis/` vs `services/` split is the load-bearing boundary.**
`analysis/` is pure and testable without fixtures or network. `services/` does
the I/O. A new detector belongs in one of them, not straddling both.

---

## Data flow, in one line each

1. Browser `POST /scan` with a repo URL
2. `api_guard` rate-limits, then validates the URL (this is the trust boundary)
3. A scan row is created; the job is dispatched (eagerly, unless a broker exists)
4. The repo is cloned into a persistent per-repo cache, or refreshed if cached
5. `analyze_repository` parses every file; a re-scan only re-parses changed files
6. Graphs are built; `RepositoryReviewEngine` assembles the report
7. The result is written to SQLite; the browser polls or streams progress

See `docs/FLOW.md` for the annotated call path with stage percentages.

---

## Trust boundaries

| Boundary | Control | Where |
|---|---|---|
| Anyone → API | `X-API-Key` when `API_KEY` is set, applied as **middleware** so new routes are protected by default | `main.py`, `api_guard.py` |
| Browser → API | CORS allowlist, never `*`; `OPTIONS` exempt from auth | `main.py` |
| User URL → `git clone` | Host allowlist, private-IP rejection, 512-char cap | `api_guard.validate_repo_url` |
| Clone → disk | Per-repo size cap, total cache ceiling, LRU eviction, clone watchdog | `disk_guard.py` |
| Abuse → resources | Per-client per-route rate limit — **in-process**, so N replicas means N× the limit | `api_guard.py` |

---

## Deliberate design decisions worth knowing

These are decisions, not accidents. Rationale in `docs/DECISIONS.md`.

- The call graph uses **stdlib Tarjan SCC, not networkx** — zero new runtime
  dependencies in the analysis layer.
- `api_guard` reads env **at call time**; `celery_app` reads at **import time**.
  The first is testable, the second is not. Copy the first.
- The clone cache keeps a **full** clone (not `--depth 1`) so re-scans can diff
  HEAD against the previous SHA and re-analyze only what changed.
- Analysis prefers **false negatives over false positives** by design — except
  in the three detectors Phase G is fixing, where that principle is currently
  inverted.

---

## Known structural weak points

- `dependency_analyzer.analyze_dependencies` — cyclomatic complexity **59**
- `repository_review_engine.review_repository` — cyclomatic complexity **58**
- The rate limiter is in-process and blocks horizontal scaling
- `frontend/src/pages/Index.tsx` is a dead placeholder
