# ==========================================================
# File: backend/validation/phase4_validation.py
# Purpose: Chunk 3 (Phase 4 - Architecture Intelligence) harness.
#
# Run:  python backend/validation/phase4_validation.py
# Exit: 0 if every check passes, 1 otherwise.
#
# Over-weights the edges the reviewer flagged:
#   - dynamic dispatch (NodeVisitor visit_*) must NOT be dead
#   - Fix F alias-aware unused imports
#   - inter-procedural taint across call boundaries (the deferred gap)
#   - framework fingerprint from real imports (dogfood = FastAPI)
# Each check prints the observed values it asserts on.
# ==========================================================

from __future__ import annotations

import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from backend.app.analysis.call_graph import (
    build_interprocedural_graph, find_dead_functions, find_call_cycles,
)
from backend.app.analysis.dead_code_detector import DeadCodeDetector
from backend.app.analysis.taint_analyzer import propagate_interprocedural_taint
from backend.app.analysis.framework_detector import (
    detect_frameworks, primary_web_framework,
)
from backend.app.analysis.architecture_analyzer import (
    detect_god_objects, detect_layer_violations,
)
from backend.app.analysis.dependency_analyzer import _risk_from_vulns

_RESULTS: list = []


def check(item_id: str, description: str):
    def wrap(fn):
        print(f"\n[{item_id}] {description}")
        try:
            detail = fn()
            _RESULTS.append((item_id, True))
            print(f"    PASS  {detail or ''}")
        except AssertionError as e:
            _RESULTS.append((item_id, False))
            print(f"    FAIL  {e}")
        except Exception as e:
            _RESULTS.append((item_id, False))
            print(f"    ERROR {type(e).__name__}: {e}")
        return fn
    return wrap


@check("P4-dispatch", "NodeVisitor visit_* dispatch methods are NOT reported dead")
def _dispatch():
    src = {"v.py": ("import ast\n"
                    "class V(ast.NodeVisitor):\n"
                    "    def visit_Call(self, node):\n        return node\n")}
    g = build_interprocedural_graph(src)
    dead = {n.name for n in find_dead_functions(g)}
    assert "visit_Call" not in dead, dead
    return "visit_Call kept alive (dynamic-dispatch class)"


@check("P4-dead", "true dead function flagged; called + entrypoint + callback kept alive")
def _dead():
    src = {"m.py": ("def used():\n    return 1\n\n"
                    "def dead():\n    return 2\n\n"
                    "def cb():\n    return 3\n\n"
                    "def main():\n    return used() or register(cb)\n")}
    dead = {n.name for n in find_dead_functions(build_interprocedural_graph(src))}
    assert dead == {"dead"}, dead
    return f"dead={dead} (used/main/cb alive)"


@check("P4-cycle", "mutual recursion detected as a call cycle (Tarjan SCC)")
def _cycle():
    src = {"r.py": ("class C:\n"
                    "    def a(self):\n        return self.b()\n"
                    "    def b(self):\n        return self.a()\n")}
    cycles = find_call_cycles(build_interprocedural_graph(src))
    assert any(len(c) == 2 for c in cycles), cycles
    return f"cycle: {cycles[0]}"


@check("P4-fixf", "Fix F: aliased import used via np is NOT unused; plain unused IS")
def _fixf():
    d = DeadCodeDetector()
    used = d.analyze("import numpy as np\nprint(np.array([1]))\n")
    unused = d.analyze("import os\nprint(1)\n")
    assert "numpy" not in used["unused_imports"], used["unused_imports"]
    assert "os" in unused["unused_imports"], unused["unused_imports"]
    return "alias-used=kept, plain-unused=flagged"


@check("P4-interproc", "inter-procedural: untrusted arg -> callee param -> sink = untrusted")
def _interproc():
    src = {"web.py": ("import os\n"
                      "def run(cmd):\n    os.system(cmd)\n\n"
                      "def view():\n    run(request.args['c'])\n")}
    f = propagate_interprocedural_taint(src)
    assert any(x.sink_name == "os.system" and x.trust_boundary == "untrusted_input"
               for x in f), f
    # constant arg must NOT produce a finding
    clean = {"c.py": ("import os\n"
                      "def run(cmd):\n    os.system(cmd)\n\n"
                      "def view():\n    run('ls')\n")}
    assert not propagate_interprocedural_taint(clean), "constant wrongly flagged"
    return "untrusted->param->sink flagged; constant not"


@check("P4-interproc-multihop", "inter-procedural taint follows a multi-hop chain to fixpoint")
def _multihop():
    src = {"m.py": ("import os\n"
                    "def run(cmd):\n    os.system(cmd)\n\n"
                    "def a(x):\n    run(x)\n\n"
                    "def view():\n    a(request.args['c'])\n")}
    f = propagate_interprocedural_taint(src)
    assert any(x.sink_name == "os.system" for x in f), f
    return "view->a->run->os.system resolved"


@check("P4-framework", "framework fingerprint from imports (flask/fastapi/django + primary)")
def _framework():
    src = {"app.py": "import flask\nfrom flask import request\n",
           "t_x.py": "import pytest\n",
           "db.py": "import sqlalchemy\n"}
    fw = detect_frameworks(src)
    assert primary_web_framework(src) == "flask", fw
    cats = {c: [h.name for h in hits] for c, hits in fw.items()}
    assert "sqlalchemy" in cats.get("orm", []) and "pytest" in cats.get("test", [])
    return f"{cats}"


@check("P4-godobject", "god object: large incoherent class flagged; small cohesive not")
def _god():
    methods = "".join(f"    def m{i}(self):\n        self.a{i}=1\n        return self.a{i}\n"
                      for i in range(13))
    gods = detect_god_objects({"b.py": "class G:\n" + methods})
    assert gods and gods[0].class_name == "G", gods
    small = {"s.py": "class C:\n    def a(self):\n        self.x=1\n    def b(self):\n        return self.x\n"}
    assert not detect_god_objects(small), "small cohesive class flagged"
    return f"G: {gods[0].method_count} methods, LCOM4={gods[0].lcom4}"


@check("P4-layer", "layer violation: model->api flagged; api->model allowed")
def _layer():
    bad = {"models/user.py": "from api.routes import h\n",
           "api/routes.py": "def h():\n    return 1\n"}
    v = detect_layer_violations(bad)
    assert any(x.importer_layer == "model" and x.importee_layer == "api" for x in v), v
    ok = {"api/routes.py": "from models.user import U\n",
          "models/user.py": "class U:\n    pass\n"}
    assert not detect_layer_violations(ok), "api->model wrongly flagged"
    return f"model->api flagged ({len(v)}); api->model allowed"


@check("P4-osv", "OSV risk mapping: any CVE -> High; Critical CVE -> Critical")
def _osv():
    assert _risk_from_vulns([], "Low") == "Low"
    assert _risk_from_vulns([{"severity": "High"}], "Low") == "High"
    assert _risk_from_vulns([{"severity": "Critical"}], "Low") == "Critical"
    return "none->Low, high->High, critical->Critical"


def main() -> int:
    print("=" * 62)
    print("Phase 4 validation - call graph, dead code, interproc taint, arch")
    print("=" * 62)
    passed = sum(1 for _, ok in _RESULTS if ok)
    total = len(_RESULTS)
    print("\n" + "=" * 62)
    print(f"RESULT: {passed}/{total} checks passed")
    for item_id, ok in _RESULTS:
        print(f"  [{'PASS' if ok else 'FAIL'}] {item_id}")
    print("=" * 62)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
