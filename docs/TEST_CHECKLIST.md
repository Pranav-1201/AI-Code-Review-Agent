# TEST CHECKLIST — proof, not claims

Nothing counts as done until these run and show the expected result **in the
current session**. "The AI said it passed" and "the code works" are two
different facts.

All commands assume the repo root, `D:\ETPROJECT`. The interpreter is the
**repo-root** venv — not `backend/venv`, which does not exist.

---

## The four gates

Run all four before calling any change complete.

### 1. Backend suite

```
venv/Scripts/python.exe -m pytest backend/tests -q
```

**Expected:** `326 passed` (baseline as of 2026-08-19, commit `06de9fc`), 3
deprecation warnings from `test_retrieval.py`, roughly 23 seconds.

The warnings are SWIG-related and pre-existing. A *rising* count is fine and
expected as work lands — a *falling* count means tests were deleted or are being
skipped, which needs an explanation.

### 2. Frontend suite

```
cd frontend && npx vitest run
```

**Expected:** `39 passed`, 5 test files
(`routes.test.ts`, `response-mapper.test.ts`, `useDocumentHead.test.ts`,
`RouteHead.test.tsx`, `ErrorBoundary.test.tsx`), around 23 seconds.

### 3. Typecheck

```
cd frontend && npx tsc --noEmit
```

**Expected:** exit code 0, no output. Any output at all is a failure.

### 4. Production build

```
cd frontend && npm run build
```

**Expected:** `✓ built in ~4.5s`. Watch the chunk sizes in the output —
`Visualizations` is currently 432.04 kB and `index` is 390.52 kB. A new chunk
above ~250 kB deserves a look before it ships.

---

## Targeted checks

### Dev launcher and CORS (guards the fix in `03dccba`)

```
venv/Scripts/python.exe -m pytest backend/tests/test_api_security.py -k vite -q
```

**Expected:** `2 passed`. These assert that the Vite port appears in the backend
CORS allowlist and that `strictPort` stays on. They are in two different
languages with nothing else connecting them, which is exactly how they drifted
apart and broke the app.

### Live end-to-end (when a change touches the HTTP boundary)

Start the backend, then:

```
curl -s -X OPTIONS http://127.0.0.1:8000/scan \
  -H "Origin: http://localhost:8080" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type" -i | head -3
```

**Expected:** `HTTP/1.1 200 OK` with an
`access-control-allow-origin: http://localhost:8080` header.

A `400` with body `Disallowed CORS origin` means the browser origin is outside
the allowlist — check which port Vite actually took.

```
curl -s -X POST http://127.0.0.1:8000/scan \
  -H "Origin: http://localhost:8080" -H "Content-Type: application/json" \
  -d '{"repo_path":"https://github.com/psf/requests"}'
```

**Expected:** `200` and a JSON body containing a real `scan_id` UUID.

### Analyzer accuracy (required for Phase G, and after any detector change)

The regression that matters is not the unit suite — it is behaviour on real
repositories. Re-run the comparison from
`docs/ANALYZER_ACCURACY_2026-08.md`:

1. Scan `pallets/flask` at `d318b683`.
   **Expected after Phase G: 0 security findings.** Today it produces 5, all
   false.
2. Scan the RL project at `54e0b4e8`.
   **Expected after Phase G: 0 SQL Injection findings.** Today it produces 2,
   both matching English prose.
3. Benchmark gate:
   ```
   venv/Scripts/python.exe backend/benchmark/run_benchmark.py
   ```
   **Expected:** no finding type below its floor in
   `backend/benchmark/corpus/thresholds.json`.

**A passing gate is not the same as a correct detector.** Every floor currently
reads 1.00 while `subprocess.run(["git", *args])` is still misreported, because
the fixture uses a literal list and real code does not. When you fix a detector,
add the real-world shape to the corpus and *then* raise the floor.

---

## CI

CI is the authority for anything involving containers, because this machine has
no Docker.

- `.github/workflows/ci.yml` — the suites plus a `deploy-stack` job that builds
  both images and boots the compose stack.
- `.github/workflows/release.yml` — publishes sha-tagged images to GHCR.

**Never claim the compose stack works based on a local check.** It cannot be
checked locally here. Push the branch and read the CI run.

---

## Before calling a phase done

- [ ] All four gates green, output pasted, from this session
- [ ] New behaviour has a test that **failed before the fix** — a test written
      after the fact proves only that it matches the code
- [ ] `git diff` read line by line, not just the summary
- [ ] `docs/HANDOVER.md` sections 1 and 3 updated
- [ ] `docs/DECISIONS.md` appended if a real decision was made
- [ ] No AI attribution in any commit message
