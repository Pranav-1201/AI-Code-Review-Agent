# SDD ledger — plan: docs/superpowers/plans/2026-08-25-j3-code-panes.md

Spec: docs/superpowers/specs/2026-08-25-j3-code-panes-design.md (read, reachable)
Branch: phase-j/j3-code-panes · BASE at start: 125a0e3
Baselines measured this session before any change: pytest 432 passed, vitest 70 passed / 11 files

**Workspace warning:** `.superpowers/sdd/.gitignore` ignores this directory with
a bare `*`, so this ledger never enters git and dies on a clean. J1's handover
pointed at a ledger that was already gone. **Copy this file to
`docs/superpowers/records/` before deleting the workspace.**

## Pre-flight conflict scan

Pairs sharing a file or an interface:

| Pair | Produced → consumed | Finding |
|---|---|---|
| T1 → T2 | `generate_refactor()["changes"]` → `refactor_result.get("changes", [])` | agree |
| T2 → T3 | `refactor_changes` (snake_case, `line_count`) → `f.refactor_changes`, `c.line_count` | agree |
| T3 → T5, T6 | `RefactorChange.lineCount` (camel) → `change.lineCount` | agree |
| T4 → T5 | `CodeViewer({code, isPatch, highlightedLines})` → called with `highlightedLines` | agree |
| T4 → T6 | same → called with `isPatch` | agree |
| T4, T5, T6 all edit `FileAnalysis.tsx` | sequential, each touches a different region (inline viewer / improved tab / patch tab) | no conflict; order T4→T5→T6 is mandatory and the plan states it |
| T5, T6 → T7 | tab labels "Suggested edits", "What changed" → asserted by the page test and the e2e | agree |

Per-task self-agreement:

| Task | Tests vs. code it specifies | Finding |
|---|---|---|
| T1 | 7 tests, all against `result["changes"]` / `result["explanation"]`, both returned by the specified code. Hand-checked the arithmetic: 3-function fixture lands docstrings at improved lines 2, 6, 10; the multi-line docstring spans exactly lines 2–8 with `total = a + b` at 9 | agree |
| T2 | asserts `kinds == {"docstring","return_hint"}`; the fixture `def hello(): print(...)` triggers both transforms | agree |
| T3 | normalizer drops kind `wat`, target `module`, line `0`; keeps the valid record | agree |
| T4 | creates `CodeViewer.tsx`, then deletes the inline copy in the same task — additive checkpoint, tree never red | agree |
| T5 | `useMemo` precedes the early return, so hook order is stable across both states | agree |
| T6 | returns `null` when no changes and no patch; test asserts empty DOM | agree |
| T7 | mock-data line numbers 2 and 7 counted against the existing `improved_code` string while planning | agree |

Test-count arithmetic across tasks: backend 432 → 439 (T1) → 440 (T2);
frontend 70 → 73 (T3) → 78 (T4) → 84 (T5) → 90 (T6) → >90 (T7). The per-task
expected counts in the plan match this chain.

**One risk carried, not a conflict:** T6's collapsed-content assertion depends
on whether Radix keeps `CollapsibleContent` mounted while closed. The plan
already tells the implementer to assert on `aria-expanded` alone if so, and to
say so rather than loosen the test.

**A concern I checked and discarded:** the `getByText` assertions in T6 look
like they would match both a `<li>` and its `<code>` child and throw on
multiple matches. They do not — Testing Library's `getNodeText` joins only an
element's *direct* text children, so `<code>Widget</code>` and its parent
`<li>` match different queries. No change needed.

Scan result: no conflicts requiring a ruling. Proceeding to Task 1.

## Progress

Task 1: implemented (commit 81b3fe6). Implementer status DONE, no concerns.
  Pre-change run confirmed 7 failures (6x KeyError 'changes' + the "to 0 " summary bug observed live).
  pytest 439 passed / 0 failed (baseline 432 + 7 new). Junk files `None` and `Tuple[str` deleted before commit.
  Task review dispatched (sonnet) over 125a0e3..81b3fe6, asked to challenge the plan's own code.
Task 1: review clean — Spec ✅ (every requirement met, nothing extra), quality approved.
  Reviewer verified the line arithmetic BY HAND (two-function trace, second docstring at improved line 11) and
  reasoned out that ascending-vs-descending insertion emits byte-identical text. Both were the risks worth paying for.
  Reviewer went idle once without reporting; chased once, verdict then arrived. Not banked as clean until received.
  Minor (deferred → resolved): stray 0-byte untracked `assert` at repo root, created after the commit.
  Controller deleted it (tree hygiene, not a code fix); `git status --short` clean.
Task 1: complete (commits 125a0e3..81b3fe6, review clean)
Task 2: implemented (commit 8bab129). Implementer went IDLE without reporting; artifacts chased instead of the
  status line — commit present, tree clean, report file written. pytest 440 passed / 0 failed (bar was >=440).
  Pre-change failure confirmed in its report.
Task 2: DEFECT FOUND BY CONTROLLER, NOT YET FIXED — the commit subject of 8bab129 begins with a UTF-8 BOM
  (bytes ef bb bf, verified with `git log -1 --format=%s | xxd`). Cause is the known Windows trap: a commit
  message file written with `Set-Content -Encoding utf8` gets a BOM, and `git commit -F` takes it literally.
  The commit is UNPUSHED, so `git commit --amend -F <clean file>` fixes it with no history rewrite of
  published work. MUST be fixed before this branch merges — the BOM is visible in the subject line forever.
Task 2: task review NOT YET RUN (session hit a usage checkpoint before dispatch).
Task 2: BOM DEFECT FIXED by controller — `git commit --amend -F <clean file written with the editor, not the shell>`.
  8bab129 -> 08de6d5. Subject now starts with bytes 43 61 ("Ca"), verified with `git log -1 --format=%s | xxd`.
  Unpushed, so no published history was rewritten. Reviewer told the report's SHA is stale by design.
  Ruling: controller fixed this rather than the implementer — it is a commit-metadata repair, not a code change,
  so it skips no code review. Cost if wrong: none; the diff is byte-identical, only the message changed.
Task 2: review dispatched (sonnet) over 81b3fe6..08de6d5.
Task 2: review clean — Spec ✅ (6/6), quality approved, no findings.
  TWO PLAN DEFECTS found by the reviewer, both already correctly handled by the implementer:
  (a) The brief named two write sites in analyze_single_file, but result["file_reports"] is assembled by a THIRD
      dict in review_repository (~line 493) that copies keys one at a time. Without that spot the test cannot pass.
      My plan's Files section was incomplete; the implementer filled the gap instead of deviating. Same file, so
      the two-file constraint held.
  (b) Cache version bumped v3.5 -> v3.6. _cache_manager keys on (code, imports, version), so any file cached under
      v3.5 would replay the old shape with no refactor_changes forever. My plan never mentioned the cache at all.
      This is the same "additive/optional" risk the spec worried about, arriving from the cache side.
  Lesson carried forward: when a field is added to a report dict in this repo, check for (i) sibling assembly sites
  that copy keys individually and (ii) the analysis cache version. Frontend tasks 3-7 have neither, so no action.
  Reviewer also adjudicated my `.get("changes", [])` question: correct defensive practice, NOT dead code — the
  fallback dict and the cache are two other producers of that shape, and Task 1's guarantee covers neither.
Task 2: complete (commits 81b3fe6..08de6d5, review clean)
Task 3: implemented (commit 0ce3f63). vitest 73 passed / 0 failed (70 -> 73), typecheck (tsc -b) exit 0.
  Pre-change run confirmed all 3 new tests failed on `refactorChanges` undefined. Tree clean, no junk, subject BOM-free.
  PLAN DEFECT (third one): my brief's PROSE called the file interface `FileRecord`; the real exported name is
  `FileAnalysis`. My own code blocks used the right name, so the implementer followed the code and flagged the prose.
  Ruling: the code is authoritative, `FileAnalysis` is correct, no rework. Carried into tasks 4-6 dispatches.
  Cost if wrong: none — the name was never written into the tree, only into my prose.
Task 3: review found 2 CRITICAL, both in normalizer code my plan specified verbatim.
  (1) `Number.isFinite(line) && line >= 1` accepts line 1.5 — a non-integer 1-based line reaches the UI.
  (2) No upper bound: line_count 1e9 passes through, and Task 5 expands each record into a Set of line
      numbers, so one corrupt record freezes the browser.
  Ruling: reviewer is RIGHT, my plan text is wrong. The spec's binding requirement is that malformed records
  are neutralised at this boundary; both of these are malformed records surviving it. Fix rather than park.
  Ruling on the SHAPE of the fix: `line` says WHERE (nonsense -> drop the whole record; integer in [1, 1e6]);
  `lineCount` says HOW MANY (nonsense -> degrade to the safe minimum 1; integer in [1, 10_000]), which matches
  what the code already does for 0 and negatives. Bounds as named constants, not inlined magic numbers.
  Cost if wrong: a legitimate change on a line past 1e6, or spanning >10k lines, would be silently dropped or
  clamped. No real Python file reaches either bound, and the alternative is a browser-freeze vector.
  Important (deferred, NOT in the loop): `refactorChanges?:` is optional but the mapper always emits an array,
  so Tasks 5-6 will contain dead `?? []` guards. Carried into their dispatches as a note, not a change.
Task 3: fix round 1/5 dispatched to the original implementer (context intact), 4 new tests required to fail first.
Task 3: fix round 1/5 (2 addressed, 0 open; commits 0ce3f63..c81c52a). Re-review confirmed the required SHAPE,
  not just that the hostile input stopped: bad `line` drops the record, bad `lineCount` keeps it and degrades to 1,
  bounds are named constants. Tests 3-4 assert KEPT-with-lineCount-1, not dropped. No pre-existing test weakened.
  Re-reviewer went idle without reporting; chased once, verdict then arrived. Not banked until received.
  vitest 77 passed / 0 failed. All 4 new tests failed against the pre-fix code first.
Task 3: complete (commits 08de6d5..c81c52a, review clean after 1 fix round)
NOTE FOR REMAINING TASKS: the frontend suite is now 77, NOT the 70+N the plan's per-task tables predict.
  The plan's expected counts are stale by +4 from here on. Correct bars: T4 -> 82, T5 -> 88, T6 -> 94, T7 -> >94.
Task 4: implemented (commit e430f80). vitest 82 passed / 0 failed / 12 files, typecheck exit 0.
  Implementer independently confirmed the corrected 77 baseline before starting. Step-2 failure was
  module-not-found with 0 tests run. No junk files, no BOM. Review dispatched over c81c52a..e430f80.
Task 4: review dispatched, reviewer went IDLE without reporting; chased once. Verdict NOT received before the
  session hit its second usage checkpoint. Task 4 is therefore IMPLEMENTED BUT NOT GATED — do not treat it as
  complete. Resume by re-reading review-c81c52a..e430f80.diff and either re-dispatching a reviewer or
  adjudicating it directly; the constitution's rule is that an unreported review is absent, never banked as clean.
STATE AT CHECKPOINT 2: branch phase-j/j3-code-panes, HEAD e430f80, tree clean.
  Tasks 1,2,3 complete and gated. Task 4 implemented, ungated. Tasks 5,6,7 not started (briefs already written).
  Counts: pytest 440 passed; vitest 82 passed / 12 files; typecheck exit 0.
Task 4: review ARRIVED after the chase — Spec ✅, quality approved, NO findings. Supersedes the "ungated" note above.
  Reviewer did the line-by-line comparison of the moved patch branch vs the deleted original: the
  +/+++, -/---, @@, else chain is identical in order, conditions and every class string. Confirmed the inline
  const was really deleted (only the import and 3 call sites remain), that `cn()` output is set-equivalent to the
  old template literal for all three existing call sites, and that the marking column does NOT render when
  highlightedLines is omitted — so neither pre-existing pane shifted. Non-colour cue is three signals
  (data-changed attribute, "+" gutter char, sr-only "Changed line."). No BOM, no attribution.
Task 4: complete (commits c81c52a..e430f80, review clean)
STATE: Tasks 1-4 complete and gated. Tasks 5-7 not started. HEAD d15d02e (ledger preservation commit).
