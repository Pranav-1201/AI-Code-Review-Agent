# J1 — Explanation parity

**Date:** 2026-08-20 · **Author:** Pranav Upadhyay · **Model in the chair:** Claude Opus 5
**Phase:** J (explanation UX), sub-phase 1 of 3
**Status:** design approved, awaiting implementation plan

---

## Why this exists

Phase J in `docs/STAFF_AUDIT_2026-08-19.md` bundles seven ideas (F4, F5, F6, F7,
F8, F9, F15) and budgets three sessions. It is too large for one design, so it
is split into three sub-phases. This document specifies **J1 only**.

The exploration that produced this split found something that changes the shape
of the work:

> Every field Phase J wants to show already exists, is already populated
> deterministically by the backend, and is already rendered correctly on **one**
> page. The other two pages simply do not read it.

| Page | `why_it_matters` | `how_to_fix` | `confidence` | `trust_boundary` |
|---|---|---|---|---|
| `FileAnalysis.tsx:266-281` | rendered as "Context:" | rendered as "Fix:" | rendered as "% Match" | rendered |
| `SecurityReport.tsx` | **missing** | **missing** (shows `recommendation` only) | **missing** | rendered |
| `IssueExplorer.tsx` | **missing** | **missing** | **missing** | rendered |

Backend sources: `repository_review_engine.py:193,204,217,353,361` and
`security_analyzer.py:394-429`. Frontend types already carry all four fields on
both `FileIssue` and `SecurityVulnerability` (`frontend/src/lib/types.ts:8-31`).

So J1 is **an extraction, not a new build**: take the treatment that already
works on `FileAnalysis`, make it a component, and adopt it where it is missing.

## Scope

**In:** F7 (security findings explain why they matter), F8 (AI Suggestions reads
as plain language), F15 (the security count means one thing), and the *detail*
half of F9 (issues carry full detail and remediation).

**Out:** F6 (clickable severity tiers) and F9's expand/collapse interaction —
both go to **J2**, which has one host to attach to once `FindingCard` exists.
F4 and F5 (the code panes) go to **J3**.

**No backend change. No LLM involvement. No new runtime dependency**
(Constraint 7).

## Architecture

`FileAnalysis.tsx:266-281` is the reference implementation and remains the
source of truth for the visual treatment. Two new units extract it:

### `frontend/src/lib/findings.ts`

Pure transforms, no React import — the same shape as `response-mapper.ts`, and
consistent with the `routes.ts` precedent in Constraint 17. Testable without
jsdom.

```ts
export interface FindingView {
  title: string;             // vuln.type | issue.message
  detail?: string;           // vuln.description; issues have none
  severity: Severity;
  category?: string;         // issue.category; "security" for vulnerabilities
  fileName?: string;
  filePath?: string;
  line?: number;
  whyItMatters?: string;
  howToFix?: string;         // how_to_fix ?? recommendation
  confidence?: number;
  trustBoundary?: string;
}

export function fromSecurityVulnerability(v: SecurityVulnerability): FindingView;
export function fromFileIssue(i: FileIssue, file: FileAnalysis): FindingView;
```

### `frontend/src/components/FindingCard.tsx`

Presentational. Takes one `FindingView`, knows nothing about scans. Renders:

`SeverityBadge` · title · detail · `Context:` line · highlighted fix box ·
badge row (file · category · `L{line}` · `TrustBoundaryBadge` · `{n}% Match`).

The backend also populates a `snippet` field on both finding types. Nothing
renders it today and `FindingView` deliberately omits it — a code excerpt needs
its own layout and truncation decisions, which belong with J2's expandable
detail, not in a card that must stay compact in a list.

**The fix box takes `how_to_fix ?? recommendation`.** This keeps
`SecurityReport`'s highlighted-box treatment, which is better than
`FileAnalysis`'s inline "Fix:" line, while gaining `FileAnalysis`'s
`why_it_matters` and confidence. Neither page loses anything it renders today.

### Data flow

`ScanReport.files[]` → `flatMap` → normalizer → `FindingView[]` → `FindingCard`.

Filtering, sorting and search stay in the pages. The card is a leaf.

## The missing-data rule

Every optional field renders **nothing** when absent — no empty label, no
"N/A", no placeholder dash. This matches `ExplanationSourceBadge`, which
already returns `null` for an unknown source.

This is pinned by a test rather than left to review, because it is the
behaviour that rots silently: a label that renders with no value beside it
looks like a bug in the analyzer rather than an absent field.

## F8 — AI Suggestions

Two narrow defects, no new prose.

1. **Literal markdown on screen.** `heuristic_refactor_engine.py:278-280`
   appends `**Suggested improvements (unapplied):** …` into the plain-text
   `explanation` string. `AISuggestions.tsx:40` renders `explanation` in a bare
   `<p>`, so the asterisks display verbatim. Fix: render it exactly as
   `FileAnalysis.tsx:255-259` already does, through
   `<ReactMarkdown rehypePlugins={[rehypeSanitize]}>`. `react-markdown@^10.1.0`
   and `rehype-sanitize@^6.0.0` are already dependencies
   (`frontend/package.json:59,63`), so this adds nothing and makes the two pages
   that render `explanation` render it the same way.

   An earlier draft of this spec proposed splitting the string on the marker
   instead, on the belief that a markdown renderer would mean a new dependency.
   That was wrong — the renderer is already here and already used for this exact
   field. The simpler fix is also the consistent one.

2. **Unlabelled provenance.** `FileAnalysis.tsx:252` already attaches
   `<ExplanationSourceBadge source={file.explanationSource} />`; this page does
   not, so a reader cannot tell rule-based prose from LLM prose on the one page
   named "AI Suggestions". Attach the same badge.

Neither change gives the LLM layer any new authority (Constraint 18).

## F15 — one count, one meaning

**Current state.** The production-only filter is applied in the *backend* at
`repository_review_engine.py:512-514`, under the comment "Security issues:
count only from production files". `total_security_issues` then feeds the
backend's own `health_score` (`sec_score` at `:570`, `health_score` at `:574`),
at 25% weight. `response-mapper.ts:22-23` mirrors the same filter as its
fallback. Meanwhile `SecurityReport.tsx:17` counts `files.flatMap(f =>
f.security)` — every file. The tile and the page it links to can disagree.

**Decision: keep the production-only scoping; fix the labelling and the
inconsistency.** The scoping is deliberate, not accidental, and two facts make
widening it the wrong move right now:

- `health_score` would move for every repository with findings in test files.
- **S9 (fixture exclusion) is still unstarted** in Phase L. This repository's own
  `backend/benchmark/corpus/fixtures/` holds deliberately vulnerable code, which
  an all-files count would pull into the headline number until S9 lands.

**Changes, all frontend:**

- `SecurityReport.tsx` scopes its list to production files; headline reads
  "N findings in production files".
- When M > 0 findings exist outside production, a muted line reads
  "M further findings in test/non-code files" — scoped, not hidden.
- `ScanResults.tsx:80,105` relabels the tile to "Security (production)".

Backend untouched. `health_score` unmoved. No dependency on S9.

## Error handling

`FindingCard` is pure presentation over an all-optional type and has no failure
mode of its own. Page-level failures remain the existing `ErrorBoundary`'s job.

## Testing

TDD throughout, each test watched failing before its implementation exists — a
fixture that passes both before and after a change measures nothing.

| File | What it pins |
|---|---|
| `src/lib/findings.test.ts` | both normalizers; `how_to_fix` preferred over `recommendation`; absent fields stay `undefined` |
| `src/components/FindingCard.test.tsx` | why / fix / confidence render when present; **no label renders at all** when absent |
| `src/pages/SecurityReport.test.tsx` | production scoping, and the "M further findings" line — the repository's first page-level test |

**Verification commands:**

- `npx vitest run` → green, from `frontend/`
- `npm run typecheck` → exit 0. **Never `tsc --noEmit`** — `frontend/tsconfig.json`
  is solution-style (`"files": []` plus `references`), so `--noEmit` compiles an
  empty program and reports success (HANDOVER §4, DECISIONS D16).
- Recorded click-through, per the Phase J acceptance row in the staff audit.

## Commit sequence

One logical change per commit (Constraint 9), explicit paths only (Constraint 2).

1. `findings.ts` + its tests — normalizers only, no UI
2. `FindingCard.tsx` + its tests
3. `SecurityReport` adopts `FindingCard` — **F7**
4. `IssueExplorer` adopts `FindingCard` — **F9 detail**
5. `AISuggestions` markdown fix + provenance badge — **F8**
6. F15 scoping and labels
7. `FileAnalysis` swaps its inline block for `FindingCard`, removing the
   duplication — **last**, as an additive checkpoint (Constraint 16), so a
   regression in the reference page cannot block the six commits that matter.

## Decisions carried forward to J3

Settled during this brainstorm; recorded here so J3 does not re-litigate them.

- **F5's prose is deterministic.** Replace the string-counting in
  `heuristic_refactor_engine.py:265-281` — which counts `"""` occurrences ÷ 2 and
  `-> None:` occurrences, and miscounts single-line docstrings — with a
  structured list of the transforms the engine knows it applied. The frontend
  renders that. It works with the LLM layer off, which is its default state.
- **F4's empty state is specific, not reassuring.** The improved pane is empty
  because the engine only applies two transforms (missing docstrings, return
  type hints — `heuristic_refactor_engine.py:216-226`), not because the file is
  clean. Copy must say so, per Constraint 21.
