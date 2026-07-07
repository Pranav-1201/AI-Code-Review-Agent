# ET Code Analyzer — System Audit (July 2026)

Ground-truth reconnaissance of the codebase as it exists on disk. Code is the source of truth;
changelogs and status notes were verified against `git diff` and were found unreliable.

---

## 1. The single most important finding

**None of the Phase 0 / Phase 1 fixes are committed.** Every claimed fix — CodeBERT gating,
SQLite scan persistence, PyPI outdated-checking, the `shell=True` dedup flag, role-aware
complexity thresholds, the SHA-1 context matrix — exists only in the *uncommitted working tree*
(8 modified files, +787/−178). At `HEAD` (`0c365d7`), the system still:

- multiplies the un-fine-tuned CodeBERT classifier output into every quality score,
- keeps scan state in an in-memory dict,
- hardcodes `is_outdated: False`,
- has no subprocess-argument classification and no SHA context awareness.

The commit messages ("Phase 2 upgrade: deterministic AST analysis…") do not describe their
contents. **And the uncommitted batch that contains the real fixes also contains two
catastrophic regressions** (§3.4, §3.A) that have never been validated together.

**Phase 2 never landed at all.** `symbol_table.py` and `cohesion_analyzer.py` do not exist
anywhere on disk. The `ParentTracker` and import-graph additions to `ast_parser.py` /
`call_graph.py` are absent. The complete Phase 2 code exists only as a draft inside
`Where i am.txt` on the Desktop — the note's own last line ("But i guess these files are not
actually added in the project") is correct.

---

## 2. System map

### 2.1 Layers and data flow (as wired today)

```
Frontend (React 18 + TS + Vite + Tailwind + shadcn/ui, Context API)
  RepositoryScanner → POST /scan {repo_path}
  poll GET /scan/{id} every 2s (5-min client deadline)   [lib/api.ts]
  response-mapper.ts normalizes → ScanReport → ScanContext → 16 pages
        │
        ▼
FastAPI app — main.py AT REPO ROOT (backend/app/routes/ is an empty stub)
  /scan → BackgroundTasks (in-process) → run_scan_pipeline
        git clone --depth 1 (+ mutates user's GLOBAL git config: http.postBuffer)
        │
        ▼
run_pipeline:
  repo_analyzer.analyze_repository        — os.walk, SEQUENTIAL per-file worker
     ├─ ast_parser.parse_python_file      — function names + imports only
     ├─ dead_code_detector                — name-set diff (alias-blind)
     ├─ complexity_analyzer               — per-function CC/depth/recursion (AST)
     └─ classify_file_type                — 5-tier roles (WT) vs production/test/… (HEAD)
  dependency_graph + call_graph           — file-level, name-bag, no resolution
  RepositoryReviewEngine.review_repository
     ├─ dependency_analyzer               — req/package/pyproject/Pipfile/setup parsing (+PyPI in WT)
     ├─ duplicate_detector                — MD5 exact + block sliding window
     └─ per file: analyze_single_file
          ├─ cache_manager (MD5 JSON file cache, key=content+imports+"v3.1")
          ├─ security_analyzer            — AST visitor, pattern rules
          ├─ llm_service.analyze_code
          │    ├─ retriever_service (FAISS+MiniLM) → context (unused in deterministic mode)
          │    ├─ deterministic probability (WT) / raw CodeBERT (HEAD)
          │    ├─ _heuristic_analysis     — depth/branching/length/__main__-guard rules
          │    ├─ quality_scorer          — 100 − ai_pen − cc_pen − sec_pen (+bonus)
          │    └─ template explanation + suggestions (deterministic strings)
          ├─ llm_refactor_engine          — heuristic docstring/`-> None` insertion + diff patch
          └─ report_generator             — Rich console prints + SQLite save_review
                                            (repo_name="local_repo", commit_id="latest")
  aggregation → summary/health_score/insights → scan_manager.complete_scan (SQLite in WT)
```

### 2.2 Real vs stubbed vs aspirational

| Component | Status |
|---|---|
| Repo scan pipeline, AST metrics, security patterns, duplicates, deps | **Real** (with defects listed in §3) |
| Scan persistence (SQLite WAL) | Real, **uncommitted**; no zombie-scan recovery |
| RAG retrieval | Infrastructure real, **decorative**: retrieves guideline chunks per file, output unused in deterministic mode; fallback returns `["mock_result"]` |
| ChromaDB vector store (`rag/vector_store.py`) | **Dead code** — only caller is commented out (report_generator.py:237-244); import still forces the dependency |
| "LLM refactor engine" | **Misnamed** — pure heuristics, no LLM anywhere in the runtime |
| PR review mode (`/github-webhook` → pr_review_engine) | **Non-functional** — feeds diff patch text to `ast.parse`, which always fails → zero findings, silently |
| `backend/app/routes/`, `backend/app/models/` | Empty stubs |
| `frontend/src/lib/mock-data.ts` | Dead file — imported by nothing (no offline demo mode) |
| `backend/app/services/rag_ingest.py` | Broken — imports `langchain_*` which is not in requirements.txt; parallel to `rag/ingest.py` |
| Multi-language analysis | Aspirational — non-Python files get metadata only |

### 2.3 Stale / contradictory docs (Desktop folder)

| Doc | Verdict |
|---|---|
| `Explanation/# Improved System Architecture.txt` | **Stale** — describes Streamlit frontend era. Archive. |
| `Explanation/# Explainable AI Code Review Agent.txt` | **Stale** — two-person setup guide, references `backend/app/main.py`, `models/schemas.py` that never materialized. Archive. |
| `Explanation/# Quick Start Checklist.txt` | **Stale** — same era. Archive. |
| `Where i am.txt` | **Wrong status claim** ("completed phase 2") but **valuable** — contains the full Phase 2 draft code. Keep as the Phase 2 source, then archive. |
| `ET_Analyzer_Engineering_Roadmap.docx` | **Current** — matches HEAD-era reality; the roadmap this audit follows. |
| `Flask_AI_Code_Review_Audit.docx` | **Current** — ground-truth Flask benchmark, source of regression cases. |
| `ai_code_review_agent_summary.md`, repo `README.md` | Structurally accurate, **oversell the AI**: "LLM reasoning / AI-assisted recommendations" are template strings + heuristics today. Rewrite during Phase 5. |

---

## 3. Section-2 gap analysis (verified, file:line)

Legend: **WT** = uncommitted working tree, **HEAD** = last commit.

| # | Item | Status | Evidence |
|---|---|---|---|
| 1 | CodeBERT residue | **Fixed in WT, not committed** | `ENABLE_CODEBERT` default-off gate (llm_service.py:27-51); deterministic probability (llm_service.py:100-163); no stray path re-enables raw output. HEAD has no gate at all. |
| 2 | `is_outdated` | **Fixed in WT, not committed** | PyPI JSON API (dependency_analyzer.py:34-77), PEP 440 compare (80-104), 1h in-memory TTL cache (26-27). HEAD hardcodes `False`. Cache is per-process only; fetches are sequential/synchronous. |
| 3 | Hardcoded confidence | **Partially fixed (cosmetic)** | security_analyzer.py:94-103 now varies confidence by *description-string keywords* (0.6/0.95/0.99/0.9) with default still `0.8`. A constant table keyed on strings, not signal. Real fix = Phase 3 taint reachability. |
| 4 | Complexity "undefined" | **REGRESSED in WT — worse than HEAD** | The baseline-1.0 edit swallowed the real aggregation into the `else:` branch (repo_analyzer.py:296-316): files **with** functions now report CC=0; files **without** functions hit `NameError: cc_values`. HEAD aggregation was correct but showed 0/undefined for module-only files. Also `compute_doc_coverage` returns bare `0.0` on SyntaxError vs tuple elsewhere (repo_analyzer.py:165) → unpack crash. |
| 5 | Scan-state persistence | **Fixed in WT, not committed; one gap** | SQLite + WAL (scan_manager.py:23-67). Gap: a scan interrupted by restart stays `analyzing` forever (no startup sweep → frontend polls to its 5-min deadline). Errors are stored as `status='complete'` with `result.error` (main.py:157-159) — frontend handles it (ScanContext.tsx:51-53). |
| 6 | Sequential processing | **Still broken** | Plain loop (repo_analyzer.py:371-377); `worker_args` shape hints at an abandoned pool. Per-file overhead is compounded by FAISS retrieval per file, Rich console printing per file (report_generator.py:110-163), and a DB insert per file (report_generator.py:225-231). |
| 7 | Dual vector stores | **Confirmed** | FAISS (retriever_service.py) vs ChromaDB (rag/vector_store.py); ChromaDB path dead (§2.2). Whole-file query (truncated 2000 chars) against `guidelines.txt` chunks — not function-level, not repo-aware. Two ingest scripts exist. |
| 8 | Flat 300-line threshold | **Still broken — two sites** | repository_review_engine.py:510 and llm_service.py:222 (plus a 150-line "style" nag at llm_service.py:228). No cohesion analyzer exists on disk. Flask `sessions.py` regression case would still flag. |
| 9 | `packaging` declared | **Fixed** | requirements.txt:49. New gaps found: `langchain-*` used by rag_ingest.py but undeclared; `networkx`/`gitpython`/`tree-sitter` will be needed by Phases 4–6. |
| 10 | File-level call graph | **Confirmed** | Name-bag per file (call_graph.py:78-108); dead functions = set difference of names (dead_code_detector.py:117-151). Currently *not surfaced in the UI at all* (mapper drops `dead_code`), so no overconfidence problem yet — but also zero user value. |
| 11 | shell=True dup guard | **Fixed in WT, untested** | `_handled_as_subprocess` flag (security_analyzer.py:182,277,309). No regression test pins it — the draft test exists only in `Where i am.txt`. |

### New defects found (not in the brief)

| ID | Defect | Evidence |
|---|---|---|
| A | **Health score structurally broken in WT**: 5-tier classifier emits `test/cli_parser/data_model/utility/orchestrator`, but aggregation filters on `== "production"` → `prod_results` always empty → avg quality/doc/CC = 0, security count = 0 → sec score pinned 100, health ≈ constant. | repo_analyzer.py:85-133 vs repository_review_engine.py:367,383,400-432; weights table expects `example`/`docs` which the classifier never emits (406-411) |
| B | `is_test` read from a key no producer sets → test-file scoring/security context never activates | repository_review_engine.py:30 vs repo_analyzer output dict |
| C | `_file_role` expected via `**kwargs` but never passed → every file is `utility`; incidentally suppresses the `__main__`-guard heuristic globally | llm_service.py:594-597,264-267 |
| D | Framework-context detection by substring: `"app.py" in path` matches `webapp.py`, `myapp.py` → wrong severity downgrades | security_analyzer.py:57-61 |
| E | PR review analyzes diff text as Python — always no-op | pr_review_engine.py:24-31 |
| F | Dead-code detector ignores import aliases (`import numpy as np` → "numpy unused") | dead_code_detector.py:54-60 |
| G | Every scan mutates the user's **global** git config | main.py:132 |
| H | Frontend collapses 5-tier roles back to `production` — masks backend semantics; `summary.average_quality_score ?? …` treats backend's broken `0` as valid (0 is not nullish) | response-mapper.ts:196-201,27 |
| I | Review DB rows written per file with `repo_name="local_repo", commit_id="latest"` — unqueryable, unbounded growth | report_generator.py:225-231 |
| J | `/github-webhook` has no signature verification; CORS `*`; API base hardcoded `http://localhost:8000` | main.py:44-50,229-241; api.ts:1 |
| K | Scan history is client-memory only — gone on refresh; no backend history endpoint despite persisted scans | ScanContext.tsx:32,74-88 |
| L | Analysis cache: unbounded file-count growth, no eviction; settings `performance.cache_results/parallel_analysis` are ignored by the engine | cache_manager.py; settings_manager.py:46-50 |

---

## 4. Execution plan (dependency-ordered, reviewable chunks)

**Chunk 0 — Stabilize & commit the working tree** *(blocks everything)*
1. Fix regression #4 (aggregation indentation + real 1.0 baseline + doc-coverage tuple).
2. Fix regression A with a two-field contract: keep `file_type ∈ {production, test, non_code}`
   for scoring/frontend (backward compatible) and add `file_role` (5-tier) for thresholds.
   Wire `is_test` (B) and `_file_role` (C) through the pipeline.
3. Validation script `backend/validation/phase0_1_validation.py` with regression asserts for
   items 1, 2, 4, 5, 11, A, B, C; run full existing test suite; then commit in reviewable slices.

**Chunk 1 — Land Phase 2 for real** (drafts from `Where i am.txt`, repaired + tested):
`symbol_table.py` (closure/comprehension scopes), `cohesion_analyzer.py` (LCOM4),
`ParentTracker` wired before analysis, import graph + iterative-DFS cycles + unused imports
(`__init__.py` whitelist), cohesion-gated size check replacing **both** flat thresholds
(#8), plus the draft validation suite as real tests. Fix F (alias-aware usage) here.

**Chunk 2 — Phase 3: taint analysis** — `taint_analyzer.py` (source/sink registries,
intra-procedural propagation via the symbol table), `trust_boundary` on every finding,
confidence derived from taint reachability (retires #3 for good), downgrade-not-suppress.
Validation: Flask-style `request.args → eval` = Critical; CLI-only path = Info.
Replace substring framework detection (D) with real fingerprinting groundwork.

**Chunk 3 — Phase 4: architecture intelligence** — networkx interprocedural call graph
(two-pass def/resolve) → real dead-code detection (retires #10), framework fingerprinting,
OSV.dev CVE lookup w/ 24h cache, god objects / SCC cycles / layer violations.

**Chunk 4 — Phase 5: explainability** — consolidate RAG onto **one** store (keep FAISS,
delete ChromaDB path, function/class-granularity chunks + metadata — retires #7);
Anthropic API explanations grounded in deterministic findings; per-finding 👍/👎 feedback
persisted with running precision estimates; junior/senior explanation toggle.

**Chunk 5 — Phase 6: productionization** — parallel per-file analysis (ProcessPoolExecutor;
retires #6), job queue (Celery+Redis or RQ), zombie-scan recovery sweep, incremental re-scan
via gitpython, tree-sitter JS/TS+Java structural rules, benchmark corpus (10 labeled repos,
precision/recall per finding type per release). Fix G, I, J, L here.

**Chunk 6 — Frontend overhaul** — design system + severity semantics, dashboard IA
(health → top-3 → progressive disclosure), interactive dependency graph, SSE live progress,
empty/loading/error states, a11y, responsive pass, real offline demo mode (resurrect
mock-data.ts), scan history from backend (K).

**Chunk 7 — Differentiators** — PR bot done right (fetch full files, map findings to changed
lines — fixes E), public audit gallery, static HTML/PDF export, rate-limited public API.
