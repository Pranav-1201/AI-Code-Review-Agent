# Benchmark corpus (Phase 6 / Chunk 5)

Precision/recall **per finding type**, run on every release, for the ET Code
Analyzer's **deterministic** finding engines only — the security analyzer,
dead-code detector, complexity analyzer (Python AST + tree-sitter JS/TS), and
interprocedural taint. The LLM explanation layer is deliberately excluded: its
output is not reproducible and therefore cannot gate a release.

## Two corpora, two roles

| Corpus | Location | Role | Gates CI? |
|--------|----------|------|-----------|
| **Fixtures** | `corpus/fixtures/` | curated repos with planted, exactly-known ground truth **and decoys** (things that look flaggable but must not be) | **YES** — hard gate |
| **Real repos** | `corpus/real_repos.json` | pinned public repos, spot-labelled on a hand-verified subset | No — report-only |

A benchmark that measured recall alone would rank a tool that flags *everything*
as perfect. Every fixture therefore carries **decoys** so precision (false
positives) is measured alongside recall.

### Real repos (pinned)
- **flask 3.0.3** (`c12a5d8…`) — *clean anchor*: well-engineered code; the
  question is whether the tool cries wolf on legitimate framework primitives.
- **bottle 0.13.2** (`ab49e0c…`) — *organic-mess anchor*: real high-complexity
  code whose template engine authentically uses `compile`/`eval` on template
  source. The precision probe: does the tool flag those legitimate uses?

Real repos are **report-only**: a pinned clone is a network dependency and must
never fail CI over something outside this project's control. Their numbers are
printed in their own prominent section because that is the figure a reviewer
reads.

## Running

```
python backend/benchmark/run_benchmark.py            # fixtures + real, full report
python backend/benchmark/run_benchmark.py --gate     # fixtures gate: non-zero exit on regression
python backend/benchmark/run_benchmark.py --no-real  # skip the network clone
python backend/benchmark/run_benchmark.py --dump      # raw findings per repo
```

`backend/tests/test_benchmark.py` runs the fixture gate offline inside the normal
`pytest` suite, so the release bar is enforced automatically.

## What the corpus surfaced (honest, tracked — not hidden behind 1.0s)

The fixture baselines in `thresholds.json` are the analyzer's **actual** measured
numbers, so sub-1.0 values encode real, documented behaviour rather than being
padded to look perfect:

- ~~**`unsafe_deserialization` recall 0.33**~~ — **FIXED in Phase C, now 1.00.**
  The detector matched only the plural `loads`, so `pickle.load` and `yaml.load`
  walked past it (fixture F3); the yaml arm was additionally unreachable, since
  PyYAML has no `yaml.loads`. Both sinks are now caught, `yaml.load` with an
  explicitly safe `Loader=` is not flagged, and the floor was raised 0.33 → 1.00.
  Note what the old floor was doing: set *at* the defect, it made the gate ratify
  the bug rather than catch it. A floor must be raised as soon as a defect is
  fixed, or it silently licenses the regression coming back.
- **`command_injection` precision 0.67** — a safe `subprocess.run([...], shell=False)`
  is still emitted (Low severity) as a Command Injection finding (fixture F2).
- **`dead_function` precision 0.67** — a function reachable only via the
  `if __name__ == "__main__"` entrypoint is flagged dead (fixture F6).

On the real repos the same shape shows at scale: **recall 1.00** (every
hand-labelled real issue — bottle's `pickle.loads` on cookie data, the genuinely
complex functions in both repos — is caught) but **precision ~0.46**, because the
security pass flags legitimate `compile`/`eval`/`sha1` framework primitives in
flask and bottle. That precision gap is the corpus's most useful signal.

## Adding to the corpus
1. Add a fixture repo under `corpus/fixtures/<name>/` with planted issues + decoys.
2. Run `--dump` to see what the analyzer actually reports.
3. Author the fixture's entry in `corpus/labels.json` (`expected` + `decoys`) from
   that output — every finding is either a labelled expected issue or a genuine
   false positive; never pad labels to force a passing number.
4. Set/adjust `thresholds.json` to the new measured baseline.
