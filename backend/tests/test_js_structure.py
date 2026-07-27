"""
Tree-sitter JS/TS structural-rule guards (Phase 6 / Chunk 5).

Two things are load-bearing and are tested separately:

1. The METRICS are correct — cyclomatic complexity counts JS/TS decision points
   (branches, loops, short-circuit &&/||/??, ternaries), nesting depth drives the
   time-complexity estimate, and role-aware thresholds match the Python analyzer.

2. Those metrics actually REACH the aggregated repository output. The Chunk 4
   lesson was that a feature can be correct in isolation yet silently absent from
   the real product path. test_js_metrics_reach_analyze_repository runs the whole
   repo pass and asserts a complex .js file comes out with real complexity
   (not the old 1.0 / O(1) stub), which is what every downstream consumer reads.
"""

import pytest

from backend.app.analysis import js_structure
from backend.app.services.repo_analyzer import analyze_repository


TANGLED_JS = """
function tangled(a, b) {
  if (a > 0 && b > 0) {
    for (let i = 0; i < a; i++) {
      while (b > 0) { b--; }
    }
  } else if (a < 0) {
    return -1;
  }
  return a ? 1 : 2;
}
const simple = (x) => x + 1;
class W { render() { if (this.ok) { return 1; } return 0; } }
"""


def _by_name(metrics):
    return {m["function"]: m for m in metrics}


def test_functions_extracted():
    r = js_structure.analyze(TANGLED_JS, ".js")
    assert r["functions"] == ["tangled", "simple", "render"], r["functions"]


def test_cyclomatic_complexity_counts_all_decision_points():
    m = _by_name(js_structure.analyze(TANGLED_JS, ".js")["complexity_metrics"])
    # base 1 + if + (&&) + for + while + (else if) + ternary = 7
    assert m["tangled"]["cyclomatic_complexity"] == 7
    # a bare arrow with no branches stays at the McCabe floor of 1
    assert m["simple"]["cyclomatic_complexity"] == 1
    # method with a single if -> 2
    assert m["render"]["cyclomatic_complexity"] == 2


def test_nesting_depth_drives_time_complexity():
    m = _by_name(js_structure.analyze(TANGLED_JS, ".js")["complexity_metrics"])
    assert m["tangled"]["max_loop_depth"] == 2      # for -> while
    assert m["tangled"]["time_complexity"] == "O(n^2)"
    assert m["simple"]["time_complexity"] == "O(1)"


def test_nested_function_complexity_not_folded_into_parent():
    code = """
    function outer(a) {
      if (a) { return 1; }
      const inner = (b) => { if (b) { if (b > 2) { return 2; } } return 0; };
      return inner(a);
    }
    """
    m = _by_name(js_structure.analyze(code, ".js")["complexity_metrics"])
    # outer owns only its own single `if` (+ base) -> 2, NOT inner's two ifs.
    assert m["outer"]["cyclomatic_complexity"] == 2
    assert m["inner"]["cyclomatic_complexity"] == 3


def test_typescript_is_supported():
    ts = """
    interface Foo { x: number; }
    function typed(a: number): number { if (a > 0) return a; return -a; }
    const g = <T,>(x: T): T => x;
    """
    r = js_structure.analyze(ts, ".ts")
    m = _by_name(r["complexity_metrics"])
    assert "typed" in r["functions"] and "g" in r["functions"]
    assert m["typed"]["cyclomatic_complexity"] == 2
    assert m["g"]["cyclomatic_complexity"] == 1


def test_tsx_is_supported():
    tsx = """
    const Button = ({ ok }: {ok: boolean}) => {
      if (ok) { return <b>yes</b>; }
      return <b>no</b>;
    };
    """
    m = _by_name(js_structure.analyze(tsx, ".tsx")["complexity_metrics"])
    assert m["Button"]["cyclomatic_complexity"] == 2


def test_role_aware_thresholds_match_python_analyzer():
    # tangled cc=7: 'utility' warns at 10 -> ok; 'test' warns at 5 -> warning.
    util = _by_name(js_structure.analyze(TANGLED_JS, ".js", role="utility")["complexity_metrics"])
    test = _by_name(js_structure.analyze(TANGLED_JS, ".js", role="test")["complexity_metrics"])
    assert util["tangled"]["risk_level"] == "ok"
    assert test["tangled"]["risk_level"] == "warning"


def test_non_js_extension_returns_empty():
    # .py is not a JS/TS grammar -> degraded (Python has its own AST path).
    assert js_structure.analyze("def f(): pass", ".py") == {
        "functions": [], "complexity_metrics": []
    }


def test_graceful_degrade_when_tree_sitter_unavailable(monkeypatch):
    # Simulate the optional dependency being absent at runtime: analyze must
    # return empty (previous behaviour) and never raise.
    monkeypatch.setattr(js_structure, "_get_parser", lambda grammar: None)
    out = js_structure.analyze(TANGLED_JS, ".js")
    assert out == {"functions": [], "complexity_metrics": []}


def test_js_metrics_reach_analyze_repository(tmp_path, monkeypatch):
    # PRODUCT-PATH guard: prove the metrics survive the full repo pass, not just
    # the isolated helper. Sequential to keep the assertion deterministic.
    monkeypatch.setenv("ANALYSIS_PARALLEL", "off")

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "tangled.js").write_text(TANGLED_JS, encoding="utf-8")
    (repo / "trivial.js").write_text("export const n = 1;\n", encoding="utf-8")

    files = analyze_repository(str(repo))
    by_path = {f["file_path"]: f for f in files}

    tangled = by_path["tangled.js"]
    # Real complexity, NOT the old stub (cc==1.0, max==1, O(1)).
    assert tangled["max_cyclomatic_complexity"] == 7
    assert tangled["cyclomatic_complexity"] > 1
    # File-level time complexity is aggregated by repo_analyzer's depth_map, which
    # uses the Unicode superscript ("O(n²)") — proving max_loop_depth=2 from
    # the JS pass propagated through aggregation (per-function metrics use "O(n^2)").
    assert tangled["time_complexity"] == "O(n²)"
    assert "tangled" in tangled["functions"]

    # A trivial JS file still collapses to the module baseline — the stub is only
    # wrong when there IS real complexity to report.
    assert by_path["trivial.js"]["max_cyclomatic_complexity"] in (0, 1)


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
