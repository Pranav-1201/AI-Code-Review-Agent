# J2 — Finding detail: real snippets, collapsible cards, navigable severity tiers

**Date:** 2026-08-20 · **Author:** Pranav Upadhyay · **Design model:** Claude Opus 5
**Phase:** J2, following J1 (`37f0060`, merged) · **Audit items:** F6, F9-expand, F16, snippet

---

## 1. Why this exists

Phase J serves the strategic direction in `docs/HANDOVER.md` §6: this product does
not compete on raw detection, it competes on **explanation and trust**. J1 gave
every finding the same explanation shape on every surface — `FindingCard` now
renders title, detail, why-it-matters and how-to-fix identically whether the
finding came from the security analyzer or the file-issue path.

J1 left three gaps that this phase closes.

1. **A finding says what is wrong but never shows it.** There is no evidence
   pane. The user is asked to trust a line number.
2. **Every card is fully expanded, always.** A repository with 623 findings —
   flask's real number — renders as an unreadable wall.
3. **The four severity tiles on Security Report are inert decoration.** They
   count findings and offer no way to reach them.

## 2. What we found before designing

### 2.1 The `snippet` field is a placeholder, not data

`FileIssue.snippet` and `SecurityVulnerability.snippet` exist in
`frontend/src/lib/types.ts`, are mapped in `lib/response-mapper.ts` (lines 173,
201), and are then **dropped** — `FindingView` in `lib/findings.ts` has no
`snippet` member, so nothing reaches `FindingCard`.

Reading every `snippet` value across the 523 cached scans in
`backend/app/.cache/` gives:

```
total snippet fields: 271
163  ''
  4  'Line 481 indicates: Command Injection'
  4  'Line 151 indicates: SQL Injection'
  4  'Line 33 indicates: Command Injection'
  ... every remaining non-empty value has this same shape
```

**60% empty; zero contain source code.** The producers are:

| Site | Emits |
|---|---|
| `security_analyzer.py:433` | `f"Line {line} indicates: {issue_type}"` |
| `repository_review_engine.py:356,364` | `f"Line {f.line}"` |
| `repository_review_engine.py:195,206,219` | pass-through of the above, or `""` |

Rendering that field as-is would print the line number a second time beside the
existing `Line 42` badge and restate the title. **The decision is to make the
field real rather than to render the placeholder.**

### 2.2 The source is already in hand at both producer sites

No plumbing is required.

- `SecurityAnalyzer.__init__` already stores `self._source_lines` (line 194) and
  already slices it at line 864.
- `apply_interprocedural_taint` already builds
  `sources = {r["file_path"]: r.get("content", "")}` (~line 305) before it
  constructs the findings that carry the placeholder.

### 2.3 The tiers do not sum to the list

`Severity` has **five** values. `Info` exists deliberately — `types.ts:1-6`
records that a code-exec sink proven reachable only from local operator input is
`Info`, "kept distinct so the UI does not collapse it to Low". Security Report
renders **four** tiles. An `Info` finding therefore appears in the list below
while no tile counts it, and the tiles do not sum to the headline.

This is the same defect class as audit item F14 (`healthScore` 54 vs `avg_score`
90.3). It is corrected here rather than preserved.

---

## 3. Design

Six tasks. Backend first, because the frontend snippet pane has nothing to
render until the backend produces something worth rendering.

### B1 — `snippet.py`, one function

New module `backend/app/services/snippet.py`:

```
extract_snippet(source_lines: list[str], line: int, context: int = 2) -> str
```

- Returns the flagged line plus `context` lines either side.
- Each line is prefixed with its 1-based number so the pane is self-locating.
- The common leading indent across the window is stripped, so a snippet from
  deep inside a class does not render as a column of whitespace.
- Each line is truncated to 200 characters, with a trailing `…` when truncated;
  minified or generated source must not blow up the payload or the layout.
- `source_lines` empty, or `line` out of range, or `line <= 0` → returns `""`.
  **It never returns a sentence.** The absence of evidence is rendered as
  absence, per the `FindingView` contract that absent means absent.

It is a free function in its own module, not a method, because two unrelated
call sites need it and neither should import the other.

### B2 — the two producers call it

- `security_analyzer._add_issue` (line 433) replaces the
  `f"Line {line} indicates: {issue_type}"` literal with
  `extract_snippet(self._source_lines, line)`.
- `apply_interprocedural_taint` (`repository_review_engine.py` ~356, ~364)
  replaces both `f"Line {f.line}"` literals, slicing the `sources` map it
  already holds.

The pass-through sites (`repository_review_engine.py:195,206,219`) need no
change — they forward whatever the producer emitted.

**Explicitly out of scope:** the code-quality `issues` path at line 195 has no
snippet upstream at all and will continue to emit `""`. Code-quality findings
are file- and function-scoped rather than line-scoped, so there is often no
single line to show. This is recorded, not fixed here.

### J2-3 — carry `snippet` to the view, filtering the legacy shape

`FindingView` gains `snippet?: string`. Both `fromSecurityVulnerability` and
`fromFileIssue` map it.

**A guard is mandatory, not cosmetic.** 523 cached scans exist on disk and
`ScanHistory` replays them. Every one predates B1/B2 and carries the placeholder.
Values matching

```
/^Line \d+( indicates: .+)?$/
```

are treated as absent. Without this guard, shipping J2 makes every historical
report display `Line 481 indicates: Command Injection` in a code pane.

### J2-4 — `FindingCard` collapses

Wrap the card body in the already-vendored Radix `Collapsible`
(`components/ui/collapsible.tsx`). **No new runtime dependency**, which
`docs/CONSTRAINTS.md` §7 would otherwise require asking about.

| State | Shows |
|---|---|
| Collapsed (default) | severity badge, title, badge row (file, line, category, trust boundary, confidence) |
| Expanded | the above, plus detail, Context, How to fix, and the snippet in a `<pre>` |

Collapsed by default is the point of the task: it converts the wall into a
scannable list. The badge row stays visible in both states so the collapsed list
still carries file, line and trust-boundary at a glance.

The trigger is a real `<button>` — not a `div` with an onClick — carrying
`aria-expanded` and `aria-controls` pointing at the panel id. A chevron rotates
with the state.

### J2-5 — Security Report groups by severity, tiers navigate

The findings list, today flat and in file order, is grouped Critical → High →
Medium → Low → Info. Each non-empty group gets a heading with a stable id
(`severity-critical`, `severity-high`, …).

The tile grid becomes **five** tiles (`grid-cols-2 md:grid-cols-5`), per §2.3.
Each tile with a non-zero count is an activator that scrolls to its group
heading. A zero-count tile renders as plain, non-interactive text and its group
renders nothing at all — no empty heading.

### J2-6 — F16 accessibility over what J2 adds

Applies to the interactive elements introduced by J2-4 and J2-5.

- Every new activator is keyboard-operable and shows a visible focus ring.
- The scroll target carries `tabIndex={-1}` and **receives focus** on activation.
  Scrolling alone moves the viewport but leaves a keyboard or screen-reader user
  where they were; moving focus is what actually makes the tier a navigation
  control.
- Smooth scrolling is gated on `prefers-reduced-motion`.
- Existing landmark, skip-link and heading structure is preserved.

---

## 4. Testing

| Layer | What it must prove |
|---|---|
| pytest | `extract_snippet` — happy path, first line, last line, out of range, empty source, indent stripping, long-line truncation. Both producers emit real source, and emit `""` rather than a sentence when source is unavailable. |
| vitest | The legacy-placeholder filter drops `Line 481 indicates: …` and keeps real code. `FindingCard` renders collapsed by default, exposes `aria-expanded`, and reveals the snippet on toggle. Security Report groups by severity, omits empty groups, and renders five tiles whose counts sum to the headline. |
| Playwright | Keyboard-only: tab to a tier, activate, focus lands on the group heading. Tab to a finding, activate, panel expands. |

### Acceptance gate

Following the Phase G template in `docs/HANDOVER.md` §3 — a floor, and evidence
from the session that claims it.

| Criterion | Floor |
|---|---|
| `venv\Scripts\python.exe -m pytest backend/tests -q` | ≥ 417 passed, 0 failed |
| `npx vitest run` (in `frontend/`) | ≥ 59 passed |
| `npm run typecheck` (`tsc -b`, **not** `--noEmit`) | exit 0 |
| `npm run build` | succeeds |
| `npx playwright test` | ≥ 17 passed |
| Re-scan a real repository | security findings carry real source in `snippet` |

The last row is the one that matters. Per `docs/HANDOVER.md` §3: a fixture that
passes both before and after a change is measuring nothing. The snippet tests
must be shown failing against the pre-B1 analyzer.

## 5. Risks

| Risk | Mitigation |
|---|---|
| 523 cached scans replay the placeholder into a code pane | The J2-3 regex guard, tested directly against a real cached value |
| A snippet leaks something sensitive from the scanned repo | Only public repositories are scannable (git-host allowlist, `api_guard.py`), and the snippet is a slice of source the user already has read access to |
| Minified or generated source destroys the layout | Per-line truncation in `extract_snippet` |
| Collapsing hides the explanation J1 just shipped | The badge row stays visible collapsed; the expand affordance is on the card header, the largest target on the card |

`docs/CONSTRAINTS.md` §18 is unaffected: a snippet is a deterministic slice of
source. No LLM involvement, no authority over any finding, severity or score.
