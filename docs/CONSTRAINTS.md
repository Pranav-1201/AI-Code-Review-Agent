# CONSTRAINTS — what must never happen without asking

Permission is scoped. "Allow" does not mean "allow anything". This file is the
scope. It is short on purpose; if it grows past two screens nobody will read it.

---

## Absolute — never, in any session

1. **No AI attribution anywhere that reaches GitHub.** No
   `Co-Authored-By: Claude`, no "Generated with Claude Code", no "written by AI"
   in commit messages, PR bodies, tags, releases or issue comments. Pranav is the
   sole developer of record. Code comments explaining *why* are fine — those are
   engineering rationale, not a byline. (Also in `CLAUDE.md`.)
2. **Never `git add -A` / `git add .`** The tree carries a gitignored `.env`,
   a `backend/app/.cache/` directory and stray zero-byte junk. Stage explicit
   paths, always.
3. **Never push without being asked.** Pushing is outward-facing and hard to
   undo once others fetch. Committing locally is fine when asked to commit.
4. **Never rewrite published history.** No force-push over commits that are
   already on `origin`, unless asked directly and explicitly.
5. **Never weaken a security control to make something work.** Specifically: do
   not widen CORS to `*`, do not disable the API-key middleware, do not remove
   the git-host allowlist, do not skip repo-URL validation. If a control is in
   the way, say so and ask.
6. **Never commit a secret.** `.env` is gitignored and stays that way.
   `.env.example` carries names and rationale only, never values.

---

## Process — ask before doing

7. **No new runtime dependency without asking.** The analysis layer is
   deliberately stdlib-only — the call graph uses an iterative Tarjan SCC rather
   than networkx, by an explicit decision (see `DECISIONS.md`). Adding a package
   reopens that decision.
8. **Never install analysis or dev tooling into the project venv.** Use a
   throwaway venv. Changing the project's dependency resolution invalidates every
   test result taken afterwards, and a stale environment hides the break until a
   clean install.
9. **One logical change per commit and per request.** Not "fix the analyzer" —
   one detector, one fix, one verification. Large vague diffs do not get reviewed
   properly by anyone.
10. **Plan before implementing.** For anything beyond a one-liner, state the
    approach and let it be corrected while it is still a paragraph.
11. **Never lower a benchmark threshold to make a gate pass.** A floor set at a
    known defect makes the gate ratify the bug. Fix the defect and raise the
    floor; if a floor genuinely must drop, argue for it explicitly.
12. **Do not touch the user's uncommitted work** unless the task is to commit it.

---

## Verification — non-negotiable

13. **No success claim without fresh evidence from the same session.** "Tests
    pass" requires a command run just now and its output. Prior notes are
    testimony, not evidence.
14. **A local pass is not evidence once dependency resolution changed.** After
    removing or splitting a dependency block, diff the old and new lock package
    sets before pushing.
15. **Importable is not declared.** Before importing anything in shipped code,
    grep the manifest. The dev venv carries packages CI does not install.
16. **For any restructure or rename, use additive checkpoints** — new code added
    and verified green *before* old code is removed. The tree never goes red.

---

## Scope boundaries specific to this codebase

17. **`frontend/src/lib/routes.ts` imports nothing.** It is the single route
    table, consumed by the app, the tests and the SEO build plugin. Keep it
    dependency-free or the build plugin breaks.
18. **The LLM layer is paraphrase-only and gated off by default.** It must never
    be described as detecting or reasoning about bugs, and must never be given
    authority over a finding, a severity or a score. Every finding is
    deterministic. Marketing and README copy must respect this.
19. **`backend/app/api_guard.py` holds the entire HTTP trust boundary.** New
    controls go there, in one readable file — not scattered into route bodies.
    Auth is applied as middleware so a newly added route is protected by
    default; do not convert it to a per-route dependency.
20. **Env is read at call time, not import time** in `api_guard.py`. That is a
    deliberate testability constraint. `celery_app.py` reads at import time and is
    correspondingly painful to test — do not copy that pattern.
21. **Respect the documented analysis boundaries.** `docs/` records what the
    analyzer guarantees versus where it deliberately under-reports. Those are
    boundaries, not TODOs. Do not "fix" a deliberate false-negative preference
    into a false-positive generator.
