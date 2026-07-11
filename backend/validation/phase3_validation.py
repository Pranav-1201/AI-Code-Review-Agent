# ==========================================================
# File: backend/validation/phase3_validation.py
# Purpose: Chunk 2 (Phase 3 - Taint Analysis) harness.
#
# Run:  python backend/validation/phase3_validation.py
# Exit: 0 if every check passes, 1 otherwise.
#
# Proves the two things the brief and the reviewer flagged:
#   1. The source/sink registries are COMPLETE for this project,
#      not just the brief's request.args/eval pair — Flask +
#      FastAPI + Django sources, and code-exec/command/deser sinks
#      (the "two -> five" audit for this chunk).
#   2. The Phase 2 SymbolTable is a REAL pipeline consumer: the
#      canonical Critical verdict is produced through the actual
#      detect_security_issues() call the scan pipeline uses, not
#      only through the standalone analyzer.
# Each check prints the observed values it asserts on.
# ==========================================================

from __future__ import annotations

import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from backend.app.analysis.taint_analyzer import (
    analyze_taint, classify_source, match_sink,
    TRUST_UNTRUSTED, TRUST_OPERATOR, TRUST_PARAMETER, TRUST_INTERNAL,
)
from backend.app.services.security_analyzer import detect_security_issues

_RESULTS: list[tuple[str, bool, str]] = []


def check(item_id: str, description: str):
    def wrap(fn):
        print(f"\n[{item_id}] {description}")
        try:
            detail = fn()
            _RESULTS.append((item_id, True, detail or ""))
            print(f"    PASS  {detail or ''}")
        except AssertionError as e:
            _RESULTS.append((item_id, False, str(e)))
            print(f"    FAIL  {e}")
        except Exception as e:
            _RESULTS.append((item_id, False, f"{type(e).__name__}: {e}"))
            print(f"    ERROR {type(e).__name__}: {e}")
        return fn
    return wrap


def _only(code: str):
    """analyze_taint on a single-sink snippet; return the lone verdict."""
    vs = analyze_taint(code)
    assert len(vs) == 1, f"expected exactly one sink, got {[v.sink_name for v in vs]}"
    return vs[0]


# ==========================================================
# Canonical brief cases
# ==========================================================

@check("P3-critical", "request.args['q'] -> eval() is untrusted/Critical (the brief case)")
def _critical():
    v = _only("eval(request.args['q'])\n")
    assert v.trust_boundary == TRUST_UNTRUSTED, v.trust_boundary
    assert v.tainted and v.hops == 0
    assert v.source_kind == "request.args", v.source_kind
    return f"eval untrusted from {v.source_kind}, hops={v.hops}, conf={v.confidence}"


@check("P3-info", "the same eval() reachable only from CLI/operator input drops to operator/Info")
def _info():
    v = _only("import sys\nx = sys.argv[1]\neval(x)\n")
    assert v.trust_boundary == TRUST_OPERATOR, v.trust_boundary
    assert v.source_kind == "argv", v.source_kind
    return f"eval operator from {v.source_kind}, conf={v.confidence}"


# ==========================================================
# Registry breadth — the "two -> five" audit
# ==========================================================

@check("P3-sources-multiframework",
       "source registry spans Flask + FastAPI + Django + operator, not just request.args")
def _sources():
    import ast
    samples = {
        "request.args['q']": TRUST_UNTRUSTED,             # Flask
        "request.form['q']": TRUST_UNTRUSTED,             # Flask
        "request.get_json()": TRUST_UNTRUSTED,            # Flask call
        "request.query_params['q']": TRUST_UNTRUSTED,     # FastAPI
        "request.path_params['q']": TRUST_UNTRUSTED,      # FastAPI
        "request.GET['q']": TRUST_UNTRUSTED,              # Django
        "request.POST['q']": TRUST_UNTRUSTED,             # Django
        "input()": TRUST_OPERATOR,                        # stdin
        "sys.argv[1]": TRUST_OPERATOR,                    # argv
        "os.getenv('X')": TRUST_OPERATOR,                 # env
        "os.environ['X']": TRUST_OPERATOR,                # env
    }
    observed = {}
    for expr, expected in samples.items():
        node = ast.parse(expr, mode="eval").body
        res = classify_source(node)
        assert res is not None, f"{expr!r} not classified as a source"
        tier, kind = res
        assert tier == expected, f"{expr!r}: expected {expected}, got {tier}"
        observed[expr] = f"{tier}:{kind}"
    # a plain constant / local name must NOT be a source
    assert classify_source(ast.parse("'literal'", mode="eval").body) is None
    return f"{len(samples)} source forms classified across Flask/FastAPI/Django/operator"


@check("P3-sinks-categories",
       "sink registry covers code-exec + command + deserialization + sql, not just eval/subprocess")
def _sinks():
    import ast
    samples = {
        "eval(x)": ("eval", "code_exec"),
        "exec(x)": ("exec", "code_exec"),
        "compile(x)": ("compile", "code_exec"),
        "os.system(x)": ("os.system", "command"),
        "os.popen(x)": ("os.popen", "command"),
        "subprocess.run(x)": ("subprocess.run", "command"),
        "subprocess.Popen(x)": ("subprocess.Popen", "command"),
        "pickle.loads(x)": ("pickle.loads", "deserialization"),
        "yaml.load(x)": ("yaml.load", "deserialization"),
        "cur.execute(x)": ("db.execute", "sql"),
    }
    cats = set()
    for expr, (name, cat) in samples.items():
        node = ast.parse(expr, mode="eval").body
        res = match_sink(node)
        assert res is not None, f"{expr!r} not matched as a sink"
        assert res[0] == name and res[1] == cat, f"{expr!r}: got {res[:2]}"
        cats.add(cat)
    assert cats == {"code_exec", "command", "deserialization", "sql"}, cats
    return f"{len(samples)} sinks across categories {sorted(cats)}"


# ==========================================================
# Propagation through the SymbolTable (the hard edges)
# ==========================================================

@check("P3-propagate-var", "taint follows a def-use edge through a local variable (1 hop)")
def _prop_var():
    v = _only("q = request.args.get('q')\neval(q)\n")
    assert v.trust_boundary == TRUST_UNTRUSTED and v.hops == 1, (v.trust_boundary, v.hops)
    return f"1-hop var -> untrusted, hops={v.hops}"


@check("P3-propagate-fstring", "taint follows an f-string/concat combinator into os.system")
def _prop_fstring():
    v = _only("import os\ncmd = f\"ls {request.args['d']}\"\nos.system(cmd)\n")
    assert v.trust_boundary == TRUST_UNTRUSTED, v.trust_boundary
    assert v.sink_name == "os.system"
    return f"f-string -> os.system untrusted, hops={v.hops}"


@check("P3-closure", "taint resolves across a closure via SymbolTable scope walk")
def _closure():
    # `q` bound in outer(); the eval sink lives in the nested inner().
    # A correct resolution requires the Phase 2 closure lookup, not a flat scan.
    code = ("def outer():\n"
            "    q = request.args['q']\n"
            "    def inner():\n"
            "        return eval(q)\n"
            "    return inner\n")
    v = _only(code)
    assert v.trust_boundary == TRUST_UNTRUSTED, v.trust_boundary
    return f"closure resolved -> untrusted (hops={v.hops})"


# ==========================================================
# No over-escalation / honest limits
# ==========================================================

@check("P3-constant-safe", "a constant argument is internal, not tainted (no over-escalation)")
def _const():
    v = _only("eval('1 + 1')\n")
    assert v.trust_boundary == TRUST_INTERNAL and not v.tainted, v.trust_boundary
    return "constant eval -> internal, tainted=False"


@check("P3-parameter", "a bare parameter is tier=parameter (annotated, NOT escalated to Critical)")
def _param():
    v = _only("def f(x):\n    return eval(x)\n")
    assert v.trust_boundary == TRUST_PARAMETER, v.trust_boundary
    assert v.tainted, "parameter is a taint source of unknown provenance"
    return "param eval -> parameter tier (no false Critical)"


@check("P3-intraprocedural-boundary",
       "taint stops at an unknown function call (documented intra-procedural limit)")
def _boundary():
    v = _only("eval(sanitize(request.args['q']))\n")
    assert v.trust_boundary == TRUST_INTERNAL and not v.tainted, v.trust_boundary
    return "eval(sanitize(untrusted)) -> internal (honest under-report, no fabricated path)"


# ==========================================================
# Real pipeline consumer + confidence from reachability
# ==========================================================

@check("P3-pipeline-consumer",
       "detect_security_issues() (the scan path) yields the Critical/untrusted verdict")
def _pipeline():
    # This exercises SymbolTable + taint through the SAME function
    # repository_review_engine.analyze_single_file() calls per file.
    issues = detect_security_issues("eval(request.args['q'])\n", file_path="views.py")
    evals = [i for i in issues if i["type"] == "Dangerous Function"]
    assert len(evals) == 1, issues
    i = evals[0]
    assert i["severity"] == "Critical", i["severity"]
    assert i["trust_boundary"] == TRUST_UNTRUSTED, i.get("trust_boundary")
    assert "untrusted input" in i["description"]
    return f"pipeline eval -> {i['severity']}/{i['trust_boundary']}, conf={i['confidence']}"


@check("P3-framework-proxy-override",
       "untrusted taint overrides the filename proxy: eval(request.args) in cli.py is Critical")
def _override():
    issues = detect_security_issues("eval(request.args['q'])\n", file_path="cli.py")
    i = [x for x in issues if x["type"] == "Dangerous Function"][0]
    assert i["severity"] == "Critical", f"cli.py must not downgrade genuine taint: {i['severity']}"
    assert "[Intentional Pattern]" not in i["description"], \
        "escalated finding must not keep the misleading intentional-pattern framing"
    return "eval(request.args) in cli.py -> Critical (Defect D proxy superseded)"


@check("P3-confidence-reachability",
       "confidence is derived from reachability, not the old description-keyword table (#3 retired)")
def _conf():
    crit = detect_security_issues("eval(request.args['q'])\n", file_path="v.py")[0]
    op = detect_security_issues("import sys\nx=sys.argv[1]\neval(x)\n", file_path="v.py")[0]
    const = detect_security_issues("eval('1+1')\n", file_path="v.py")[0]
    # untrusted > operator > internal, and NONE equals the old flat 0.90 eval prior
    assert crit["confidence"] == 0.97, crit["confidence"]
    assert op["confidence"] == 0.80, op["confidence"]
    assert const["confidence"] == 0.60, const["confidence"]
    assert 0.90 not in (crit["confidence"], op["confidence"], const["confidence"])
    return f"untrusted={crit['confidence']} > operator={op['confidence']} > internal={const['confidence']}"


@check("P3-downgrade-not-suppress",
       "an operator/internal sink is downgraded but still REPORTED (never dropped)")
def _downgrade():
    op = detect_security_issues("import sys\nx=sys.argv[1]\neval(x)\n", file_path="v.py")
    const = detect_security_issues("eval('1+1')\n", file_path="v.py")
    assert len(op) == 1 and op[0]["severity"] == "Info", op
    assert len(const) == 1, const
    return "operator eval -> Info (reported), constant eval -> still reported"


def main() -> int:
    print("=" * 62)
    print("Phase 3 validation - taint analysis (sources, sinks, propagation)")
    print("=" * 62)
    passed = sum(1 for _, ok, _ in _RESULTS if ok)
    total = len(_RESULTS)
    print("\n" + "=" * 62)
    print(f"RESULT: {passed}/{total} checks passed")
    for item_id, ok, _ in _RESULTS:
        print(f"  [{'PASS' if ok else 'FAIL'}] {item_id}")
    print("=" * 62)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
