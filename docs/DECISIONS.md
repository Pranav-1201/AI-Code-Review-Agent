# DECISIONS — why, not just what

Code shows what changed. This shows why. Append here whenever a real decision is
made; six months from now this is the only thing that stops a settled argument
being re-litigated.

**Format:** date · decision · reasoning · who/what decided it. Newest last.

---

### D1 — Call graph uses stdlib Tarjan SCC, not networkx
**Chunk 3** · Decided by: Pranav (sign-off) + Claude

The roadmap in `SYSTEM_AUDIT_2026-07.md` suggested networkx. We used an
iterative Tarjan SCC from the stdlib instead.

**Why:** the whole `analysis/` layer is deliberately dependency-free, which
keeps it pure, fast to import and trivial to test. Taking a graph library for
one algorithm we can write in 40 lines reopens that property for no gain.

**When to revisit:** if a future phase genuinely needs centrality or PageRank.
Take the dependency *then*, with a concrete justification. This is not an
oversight to be "fixed".

---

### D2 — `api_guard` reads environment at call time, `celery_app` at import time
**Phase A**

`api_guard.py` reads every env var inside the function that needs it.

**Why:** it lets the test suite monkeypatch `os.environ` without reloading
`main`. `celery_app.py` reads its config at import time and is correspondingly
painful to test — that is the counter-example, not the pattern. Copy
`api_guard`.

**Exception:** `CORSMiddleware` needs a fixed origin list at construction, so
`ALLOWED_ORIGINS` is read exactly once at import. Changing it requires a process
restart, and monkeypatching it in a test has no effect on the live middleware —
test `api_guard.allowed_origins` directly instead.

---

### D3 — Auth is middleware, not a per-route dependency
**Phase A**

**Why:** the failure mode of the dependency approach is a route that ships
without one and is silently public. As middleware, a newly added route is
protected by default. The cost is that public paths need an explicit allowlist
(`PUBLIC_PATHS`), which is a smaller and more visible risk.

`OPTIONS` is exempt because the browser sends preflights without custom headers
by design — requiring `X-API-Key` on them would break every cross-origin call
before the real request was made.

---

### D4 — CORS registered after auth so it sits outside it
**Phase A**

Starlette runs the last-added middleware outermost.

**Why:** a 401 still comes back with CORS headers, so the browser can surface
"unauthorized" rather than an opaque network error. Reversing the order turns
every auth failure into an unexplainable fetch error.

---

### D5 — The SSE stream accepts a key in the query string; nothing else does
**Phase A**

**Why:** the browser's `EventSource` API cannot set request headers at all, so
an authenticated deployment would have no way to open the progress stream if
`X-API-Key` were the only channel. Scoped to this one route because query
strings are logged by proxies and land in browser history — a key there is far
less private than one in a header.

---

### D6 — The clone cache keeps full history, not a shallow clone
**Phase 6 / Chunk 5**

**Why:** a re-scan diffs the previous SHA against the new HEAD and re-analyzes
only changed files. `--depth 1` would make that impossible.

**Tradeoff accepted:** disk grows with one clone per distinct repo URL. Bounded
by `disk_guard`'s LRU eviction and per-repo size cap, not by the clone strategy.

---

### D7 — Disk eviction runs outside the scan's try block
**Phase E**

**Why:** an exception during eviction would escape before `complete_scan()` ran
and strand the scan in a non-terminal state with no error shown to the user —
unlike every other failure path, which terminates cleanly. Eviction is
housekeeping, not part of the scan's contract. If a directory is locked longer
than the retry budget, log it and scan anyway.

A reviewer caught a related inversion in the eviction ordering: an entry with no
timestamp is not the least useful, it is the one a sibling worker is writing
right now. Sorting it first would delete live clones.

---

### D8 — The LLM layer is paraphrase-only and gated off
**Phase 5**

**Why:** determinism is the product's trust property. Every finding, severity
and score is computed by AST analysis. The Anthropic layer turns those into
prose and is instructed not to invent issues. Output carries
`explanation_source` = `llm` | `deterministic` so a reader always knows.

**Consequence for copy:** marketing and README must never claim the LLM "finds"
or "reasons about" bugs. The refactor engine is likewise fully deterministic AST
transforms — never describe it as AI.

---

### D9 — Analysis prefers false negatives over false positives
**Standing principle**

**Why:** a tool that cries wolf gets ignored entirely. Dynamic dispatch and
framework entrypoints are treated as ALIVE rather than risk flagging a live
handler as dead. Ambiguous cross-file names are skipped rather than guessed.

**This principle is currently inverted in three security detectors** — see D12.
That is a defect, not a change of policy.

---

### D10 — Benchmark floors are raised the moment a defect is fixed
**Phase C**

A floor set *at* a known defect makes the gate ratify the bug instead of
catching it. Phase C raised `unsafe_deserialization` recall 0.33 → 1.0 and
`command_injection` precision 0.66 → 1.0 as the underlying bugs were fixed.

**Rule:** every floor sits at 1.0. Any regression fails the gate, and a new
sub-1.0 floor must be argued for rather than inherited.

---

### D11 — Vite pins its port; the dev origin may not drift
**2026-08-19** · Claude Opus 5, session `a55eaf1f` · commit `03dccba`

Vite had `port: 8080` without `strictPort`, so a busy port sent it silently to
8081. The page still loaded, so the app looked up — but its `Origin` was no
longer in the backend's CORS allowlist and every API call died at the preflight,
showing only a bare `OPTIONS /scan 400` in the log.

**Why `strictPort` rather than widening CORS:** widening the allowlist would
weaken a Phase A security control to paper over a dev-server problem. Failing
loudly on a busy port is the smaller, more honest fix. `start.bat` now names the
PID holding the port, since a stale server from a previous run is the usual
cause.

Two tests pin the Vite port to the backend allowlist — they live in different
languages with nothing else connecting them, which is exactly how they drifted.

---

### D12 — Reposition around explanation, not detection
**2026-08-19** · Claude Opus 5, session `a55eaf1f` · recommendation, awaiting
Pranav's confirmation

An independent cross-check (bandit / radon / pyflakes / vulture) over three
pinned repositories found **5 of 5 security findings on `pallets/flask` were
false positives**, and 2 of 4 on an unrelated RL project.

**Why reposition:** Semgrep, CodeQL and Sonar are free on public repos and
materially more precise. Competing on raw detection is a losing position. The
durable differentiator is the explanation and trust model — deterministic
findings, labelled sources, trust boundaries, confidence values, and honestly
documented limits. Semgrep hands you a rule ID; this hands a junior developer a
lesson.

**Decision:** lead the product with repository health, complexity, structure,
dependencies and duplication, where it is measurably competent. Demote security
to a clearly labelled "candidates to triage" section with the precision numbers
published openly. Fix the three worst detectors anyway (Phase G) — shipping
known-wrong High-severity findings is not acceptable regardless of positioning.

**Alternative considered and not chosen:** delegate raw detection to
Semgrep/bandit and keep only the explanation layer. Best product, largest
rewrite. Revisit after Phase G if precision remains a problem.

---

### D13 — Deployment target is a single small VPS
**2026-08-19** · Claude Opus 5, session `a55eaf1f` · recommendation

**Why:** the Caddy + compose + GHCR stack already exists and needs no
re-architecture. `/scan` needs persistent disk for the clone cache and its LRU
eviction, and runs long CPU-heavy jobs — which is precisely what rules out
Vercel/Netlify/Lambda, and what makes Render/Railway's ephemeral disk a poor
fit. Fly.io is workable but scaling past one machine breaks the in-process rate
limiter and the shared-SQLite assumption.

Rough cost ~$5–7/month. **Not verified during the audit** — check current
pricing before committing.

---

### D14 — Phase G departs from its own written plan in two places
**2026-08-19** · Claude Opus 5, session `0f899c51` · implemented, verified

`HANDOVER.md` specified the three detector fixes. Two were implemented
differently from the text, deliberately, and the reasons need to outlive the
commit messages.

**S3 — not "list argv with no shell is safe".** Taken literally that clears
`subprocess.run(["sh", "-c", user])`, which is a live injection and is exactly
what Phase C had fixed after finding the analyzer describing it to the reader
as a "safe invocation pattern". The rule implemented instead is: a list argv
with `shell` not True is cleared when **either** every element is a literal
(Phase C's rule, kept) **or** argv[0] is a string literal naming a non-shell
program with no `-c` style flag present. Under `shell=False` the list goes to
execve as-is, so nothing after argv[0] can begin a new command — which is why
`["git", *args]` is inert and was being reported.

The all-constant half was not in the first implementation and had to be put
back. Rescanning a real repository found `subprocess.run(["powershell",
"-NoProfile", "-Command", "<literal>"])` still flagged, because argv[0] names a
shell. Every element was constant. **The lesson is that the real-repo rescan,
not the unit tests, caught it** — the tests only knew the cases their author
had thought of.

**S2 — SQL shape only, not sink reachability.** HANDOVER asked for statement
shape "and, better, that the value reaches a cursor/execute sink". Shape alone
is what shipped. The corpus fixture builds its query on one line and executes
it on the next (`q = "SELECT ... " + uid` / `db.execute(q)`), so gating on sink
adjacency would trade this false-positive class for a false-negative one, and
the taint layer's dataflow is not wired into these two visitors. Shape is
gated as: the string must **begin** with a SQL verb and contain a clause
keyword. Requiring the leading verb rather than matching `select ... from`
anywhere is what separates "Please select an option from the menu" from a
query.

**A fourth defect, not in the plan.** `visit_BinOp` carried the identical
substring bug to `visit_JoinedStr` — `log("Deleted user: " + name)` was a High
SQL Injection finding. Fixed in the same commit as S2.

**Known residual, accepted:** prose that genuinely begins with a SQL verb and
contains a clause word — `f"Select a template from {folder}"` — still matches.
Narrower than the class removed, and tightening further starts to cost real
queries.

**Verified:** pytest 373 passed, fixture gate 1.00 across all 11 types, flask
**0** security findings (was 5, all false positives), RLPROJECT **0** SQL
Injection and command injection 3 → 1. The new corpus fixture was checked
against the pre-Phase-G analyzer and fails it at command_injection precision
0.38 / sql_injection 0.50, so the gate is load-bearing rather than decorative.

---

### D15 — "unknown" is a first-class dependency answer
**2026-08-20** · Claude Opus 5, session `0f899c51` · implemented, verified

Phase H's three items turned out to be one decision: **the report may not
invent a version, and it may not imply a safety claim it did not earn.**

Every Python manifest parser had been stripping the operator off a specifier
and keeping the digits, so `flask>=2.0` was stored as version `2.0` — and that
invented number was then the OSV query key, producing CVEs against a version
the project may not install. The node side had already rejected this in Phase C
(`_exact_npm_version`); Python simply never got it.

**Decision:** `version` holds a concrete version or `"unknown"`, never a
constraint. Three fields carry what used to be conflated into one:

| field | meaning |
|---|---|
| `version` | a concrete version, or `unknown` |
| `constraint` | the specifier as written, e.g. `>=2.0` |
| `version_source` | `pinned` / `lockfile` / `unpinned` / `unspecified` |
| `vuln_lookup` | `checked` / `unreachable` / `skipped` |

**Why `vuln_lookup` matters more than it looks.** An empty vulnerability list
meant three different things and rendered as one green tick: OSV answered zero,
OSV was unreachable, or nothing was ever asked. A security report that cannot
distinguish "clean" from "the lookup was down" is worse than one that says
nothing, because it is believed. A failed lookup is also no longer cached — it
was being written into a 24-hour cache as an empty result, so a single timeout
reported a package clean for the rest of the day.

**Consequence accepted:** pinned `pallets/flask` now shows `unknown` for all 8
dependencies, where it used to show confident numbers. That is not a
regression. Flask pins nothing and ships no lockfile, so the honest answer is
that its installed versions are not knowable from the repository — and no CVE
claim is made in either direction. The lockfile readers (`requirements.lock`,
`uv.lock`, `poetry.lock`) mean any project that *does* pin gets real answers.

**Two bugs found on the way, neither in the plan.** The `setup.cfg` reader
decided where `install_requires` ended by testing `stripped[0].isspace()` on a
string it had already stripped — always False — and since every versioned
requirement contains `=`, the section closed on its own first line; no
setup.cfg dependency carrying a version had ever been recorded. And the PyPI
"latest release" lookup sat behind the unknown-version guard, so making
versions honest silently removed the upgrade target from every unpinned
dependency. **The acceptance criterion caught the second one, not the tests** —
the same pattern as Phase G, where the real-repo rescan caught what the unit
tests could not.

**Verified:** pytest 417 passed, `npm run typecheck` 0 errors, vitest 39
passed; against pinned flask, `latest_version` resolved **8/8**, zero
constraints in any version field, zero dependencies missing a lookup status.

---

### D16 — `tsc --noEmit` is not the frontend typecheck
**2026-08-20** · Claude Opus 5, session `0f899c51` · correction to the record

`frontend/tsconfig.json` is solution-style: `"files": []` plus `references` to
`tsconfig.app.json` and `tsconfig.node.json`. `tsc --noEmit` therefore compiles
an **empty program** and exits 0 having checked nothing — `--listFiles` prints
zero lines.

`ci.yml` has always run `tsc -b` and carries a comment explaining exactly this,
so the shipped gate was never wrong. What was wrong was the local ritual:
`HANDOVER.md` recorded `tsc --noEmit exit 0` as evidence, and this session
believed it before `tsc -b` found six real type errors in the same tree.

**Decision:** `npm run typecheck` (added, runs `tsc -b`) is the only frontend
typecheck anyone should type. A green result from a command that checks nothing
is worse than no result, because it is recorded as evidence.
