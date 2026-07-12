"""
Phase 4 architecture-intelligence unit tests: interprocedural call graph,
inter-procedural taint, framework fingerprinting, god objects / layer
violations, and the OSV risk mapping.
"""

import unittest

from backend.app.analysis.call_graph import (
    build_interprocedural_graph, find_dead_functions, find_call_cycles,
)
from backend.app.analysis.taint_analyzer import propagate_interprocedural_taint
from backend.app.analysis.framework_detector import (
    detect_frameworks, primary_web_framework,
)
from backend.app.analysis.architecture_analyzer import (
    detect_god_objects, detect_layer_violations,
)
from backend.app.analysis.dependency_analyzer import _risk_from_vulns


class TestInterproceduralCallGraph(unittest.TestCase):
    def _dead(self, src):
        return {n.name for n in find_dead_functions(build_interprocedural_graph(src))}

    def test_true_dead_flagged(self):
        src = {"m.py": "def used():\n    return 1\n\ndef dead():\n    return 2\n\n"
                       "def main():\n    return used()\n"}
        self.assertEqual(self._dead(src), {"dead"})

    def test_visitor_dispatch_not_dead(self):
        src = {"v.py": "import ast\nclass V(ast.NodeVisitor):\n"
                       "    def visit_Call(self, node):\n        return node\n"}
        self.assertNotIn("visit_Call", self._dead(src))

    def test_callback_reference_keeps_alive(self):
        src = {"c.py": "def cb():\n    return 1\n\ndef reg():\n    return register(cb)\n"}
        self.assertNotIn("cb", self._dead(src))

    def test_decorated_route_not_dead(self):
        src = {"a.py": "@app.get('/x')\ndef h():\n    return 1\n"}
        self.assertEqual(self._dead(src), set())

    def test_mutual_recursion_cycle(self):
        src = {"r.py": "class C:\n    def a(self):\n        return self.b()\n"
                       "    def b(self):\n        return self.a()\n"}
        cycles = find_call_cycles(build_interprocedural_graph(src))
        self.assertTrue(any(len(c) == 2 for c in cycles))


class TestInterproceduralTaint(unittest.TestCase):
    def test_untrusted_arg_into_param_sink(self):
        src = {"w.py": "import os\ndef run(cmd):\n    os.system(cmd)\n\n"
                       "def view():\n    run(request.args['c'])\n"}
        f = propagate_interprocedural_taint(src)
        self.assertTrue(any(x.sink_name == "os.system"
                            and x.trust_boundary == "untrusted_input" for x in f))

    def test_multihop_chain(self):
        src = {"m.py": "import os\ndef run(c):\n    os.system(c)\n\n"
                       "def a(x):\n    run(x)\n\ndef view():\n    a(request.args['c'])\n"}
        self.assertTrue(propagate_interprocedural_taint(src))

    def test_cross_file(self):
        src = {"lib.py": "def run(code):\n    eval(code)\n",
               "web.py": "from lib import run\ndef view():\n    run(request.args['q'])\n"}
        f = propagate_interprocedural_taint(src)
        self.assertTrue(any(x.sink_name == "eval" for x in f))

    def test_constant_arg_not_flagged(self):
        src = {"c.py": "import os\ndef run(c):\n    os.system(c)\n\ndef view():\n    run('ls')\n"}
        self.assertEqual(propagate_interprocedural_taint(src), [])


class TestFrameworkDetector(unittest.TestCase):
    def test_primary_web_framework(self):
        src = {"a.py": "import flask\n", "b.py": "import flask\n"}
        self.assertEqual(primary_web_framework(src), "flask")

    def test_multi_category(self):
        src = {"a.py": "import fastapi\n", "t.py": "import pytest\n", "d.py": "import sqlalchemy\n"}
        cats = {c: [h.name for h in hits] for c, hits in detect_frameworks(src).items()}
        self.assertIn("fastapi", cats.get("web", []))
        self.assertIn("pytest", cats.get("test", []))
        self.assertIn("sqlalchemy", cats.get("orm", []))

    def test_none_when_absent(self):
        self.assertEqual(primary_web_framework({"a.py": "x = 1\n"}), "none")


class TestArchitectureSmells(unittest.TestCase):
    def test_god_object_flagged(self):
        methods = "".join(f"    def m{i}(self):\n        self.a{i}=1\n        return self.a{i}\n"
                          for i in range(13))
        gods = detect_god_objects({"b.py": "class G:\n" + methods})
        self.assertTrue(gods and gods[0].class_name == "G")

    def test_small_cohesive_not_god(self):
        src = {"s.py": "class C:\n    def a(self):\n        self.x=1\n    def b(self):\n        return self.x\n"}
        self.assertEqual(detect_god_objects(src), [])

    def test_layer_violation_model_imports_api(self):
        src = {"models/user.py": "from api.routes import h\n", "api/routes.py": "def h():\n    return 1\n"}
        v = detect_layer_violations(src)
        self.assertTrue(any(x.importer_layer == "model" and x.importee_layer == "api" for x in v))

    def test_api_importing_model_is_allowed(self):
        src = {"api/routes.py": "from models.user import U\n", "models/user.py": "class U:\n    pass\n"}
        self.assertEqual(detect_layer_violations(src), [])


class TestOSVRiskMapping(unittest.TestCase):
    def test_no_vulns_keeps_current(self):
        self.assertEqual(_risk_from_vulns([], "Medium"), "Medium")

    def test_any_cve_is_high(self):
        self.assertEqual(_risk_from_vulns([{"severity": "High"}], "Low"), "High")

    def test_critical_cve_is_critical(self):
        self.assertEqual(_risk_from_vulns([{"severity": "Critical"}], "Low"), "Critical")


if __name__ == "__main__":
    unittest.main()
