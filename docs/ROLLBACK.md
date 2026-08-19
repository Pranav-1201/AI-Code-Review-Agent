# ROLLBACK — the way back out

Confidence to make big changes comes from knowing exactly how to reverse them.
Every entry gives a specific target, a command, and what to re-check afterwards.

---

## Before any risky change

1. Know the last-good commit: `git log --oneline -1`
2. Confirm the tree is clean: `git status --porcelain` (empty)
3. Confirm the four gates are green *before* you start — otherwise you cannot
   tell whether you broke it or found it broken. See `docs/TEST_CHECKLIST.md`.
4. For anything touching more than one module, work on a branch.

---

## Level 1 — uncommitted work went wrong

```
git diff                      # read it first, always
git checkout -- <path>        # one file
git stash                     # keep it, decide later
```

**Never** `git checkout .` or `git reset --hard` without reading the diff — this
tree regularly carries work the user has not asked you to touch.

**Re-check after:** the four gates.

---

## Level 2 — a commit went wrong, not yet pushed

```
git revert <sha>              # preferred: keeps history honest
git reset --soft HEAD~1       # only to re-do the commit message/staging
```

Prefer `revert` over `reset` once a commit exists. `reset --hard` discards work
with no recovery path outside the reflog.

**Re-check after:** the four gates, plus the targeted check for whatever the
commit touched.

---

## Level 3 — a commit went wrong and IS pushed

```
git revert <sha> && git push
```

**Never force-push over published commits.** A revert commit is noisier and
correct; a rewritten history breaks every clone that already fetched it. Only
rewrite if asked directly and explicitly, after saying what it will cost.

---

## Level 4 — the deployed stack is broken

The image tag is the rollback control. Both images share the tag, so API and web
move together.

1. Find a known-good sha that GHCR already holds.
2. Set `IMAGE_TAG=<sha>` in the production `.env`.
3. `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d`

**Re-check after:**
- `curl https://<domain>/health` → 200, and `auth` reads `enabled`
- one real scan completes end to end
- Sentry shows no new error class

**This rollback must be drilled once before it is trusted** — a rollback plan
that has never been executed is a document, not a plan. Phase M owns that drill.

---

## Level 5 — the scan database is corrupted or lost

SQLite with WAL, snapshotted by `scripts/backup-sqlite.sh` to a **host**
directory (`BACKUP_HOST_DIR`), deliberately — a backup living only inside Docker
dies with the Docker state you would be recovering from.

```
scripts/restore-sqlite.sh <snapshot>
```

**Re-check after:** `GET /scans` returns the expected history; a new scan
completes and persists.

Note: `BACKUP_KEEP` is what bounds that directory. Snapshots are **not** covered
by the Phase E disk ceilings, which bound the analysis caches only.

---

## Change-specific rollbacks

### The dev launcher / CORS fix (`03dccba`)

Touches `frontend/vite.config.ts`, `start.bat`,
`backend/tests/test_api_security.py`.

**Symptom that would justify reverting:** Vite now refuses to start when 8080 is
busy, by design. If that blocks someone who genuinely needs a second instance,
the fix is to free the port, not to revert — reverting restores the silent drift
that broke every API call.

```
git revert 03dccba
```
**Re-check:** `pytest backend/tests/test_api_security.py -k vite -q` → the two
tests will now *fail*, which is the expected consequence.

### Phase G detector changes (not yet made)

Highest-risk change in the plan: it alters what the product reports.

**Before:** record the current finding counts for all three reference repos
(flask 5, RL-Project 4, this repo 28) so a regression is measurable.
**Rollback:** revert the detector commit; the corpus fixtures added alongside it
can stay — they document the intended behaviour either way.
**Re-check:** `backend/benchmark/run_benchmark.py` plus a re-scan of flask.

### Anything touching `index.css` tokens (Phase I light mode)

Every component inherits these. A bad token change is visible everywhere at once
and easy to misread as many separate bugs.

**Rollback:** `git checkout -- frontend/src/index.css`
**Re-check:** load the app in light *and* dark, plus the un-stamped system
default — three states, not two.

---

## What is NOT recoverable

- **A pushed secret.** Rotate it; do not rely on a revert. Git history keeps it.
- **`git reset --hard` on uncommitted work** older than the reflog window.
- **A deleted clone cache** — harmless, it re-clones, but the next scan is slow
  and loses incremental diffing until it rebuilds a prior.
