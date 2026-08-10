"""
Phase 3 taint-analysis unit tests.

Two layers:
  1. The standalone analyzer (analyze_taint): source/sink classification
     and intra-procedural def-use propagation via the Phase 2 SymbolTable.
  2. The integrated pipeline (detect_security_issues): taint reachability
     drives severity, trust_boundary, and reachability-derived confidence —
     and must not regress the existing framework/constant behavior.
"""

import unittest

from backend.app.analysis.taint_analyzer import (
    analyze_taint, TRUST_UNTRUSTED, TRUST_OPERATOR, TRUST_PARAMETER, TRUST_INTERNAL,
)
from backend.app.services.security_analyzer import detect_security_issues


def _one(code):
    verdicts = analyze_taint(code)
    assert len(verdicts) == 1, [v.sink_name for v in verdicts]
    return verdicts[0]


class TestTaintPropagation(unittest.TestCase):
    """Standalone analyzer: sources, sinks, and def-use propagation."""

    def test_untrusted_direct_is_critical_tier(self):
        v = _one("eval(request.args['q'])\n")
        self.assertEqual(v.trust_boundary, TRUST_UNTRUSTED)
        self.assertEqual(v.hops, 0)
        self.assertTrue(v.tainted)

    def test_operator_argv_is_operator_tier(self):
        v = _one("import sys\nx = sys.argv[1]\neval(x)\n")
        self.assertEqual(v.trust_boundary, TRUST_OPERATOR)
        self.assertEqual(v.source_kind, "argv")

    def test_constant_is_internal_untainted(self):
        v = _one("eval('1 + 1')\n")
        self.assertEqual(v.trust_boundary, TRUST_INTERNAL)
        self.assertFalse(v.tainted)

    def test_bare_parameter_is_parameter_tier(self):
        v = _one("def f(x):\n    return eval(x)\n")
        self.assertEqual(v.trust_boundary, TRUST_PARAMETER)

    def test_fastapi_query_params_source(self):
        v = _one("data = request.query_params['x']\neval(data)\n")
        self.assertEqual(v.trust_boundary, TRUST_UNTRUSTED)
        self.assertIn("query_params", v.source_kind)

    def test_django_post_source(self):
        v = _one("exec(request.POST['code'])\n")
        self.assertEqual(v.trust_boundary, TRUST_UNTRUSTED)
        self.assertIn("django", v.source_kind)

    def test_propagation_through_variable(self):
        v = _one("q = request.args.get('q')\neval(q)\n")
        self.assertEqual(v.trust_boundary, TRUST_UNTRUSTED)
        self.assertEqual(v.hops, 1)

    def test_propagation_through_fstring(self):
        v = _one("import os\ncmd = f\"ls {request.args['d']}\"\nos.system(cmd)\n")
        self.assertEqual(v.trust_boundary, TRUST_UNTRUSTED)
        self.assertEqual(v.sink_name, "os.system")

    def test_propagation_through_closure(self):
        # Requires the SymbolTable closure lookup: q is bound in outer(),
        # the eval sink lives in the nested inner().
        code = ("def outer():\n"
                "    q = request.args['q']\n"
                "    def inner():\n"
                "        return eval(q)\n"
                "    return inner\n")
        v = _one(code)
        self.assertEqual(v.trust_boundary, TRUST_UNTRUSTED)

    def test_intraprocedural_boundary_stops_taint(self):
        # taint must NOT flow through an unknown function (inter-procedural).
        v = _one("eval(sanitize(request.args['q']))\n")
        self.assertEqual(v.trust_boundary, TRUST_INTERNAL)
        self.assertFalse(v.tainted)

    def test_pickle_untrusted_deserialization(self):
        v = _one("import pickle\npickle.loads(request.data)\n")
        self.assertEqual(v.category, "deserialization")
        self.assertEqual(v.trust_boundary, TRUST_UNTRUSTED)

    def test_syntax_error_returns_empty(self):
        self.assertEqual(analyze_taint("def broken(:\n"), [])


class TestTaintPipelineIntegration(unittest.TestCase):
    """detect_security_issues(): taint drives severity/confidence/trust_boundary."""

    def _eval_issue(self, code, **kw):
        issues = detect_security_issues(code, **kw)
        dangerous = [i for i in issues if i["type"] == "Dangerous Function"]
        self.assertEqual(len(dangerous), 1, issues)
        return dangerous[0]

    def test_untrusted_eval_is_critical(self):
        i = self._eval_issue("eval(request.args['q'])\n", file_path="views.py")
        self.assertEqual(i["severity"], "Critical")
        self.assertEqual(i["trust_boundary"], TRUST_UNTRUSTED)
        self.assertEqual(i["confidence"], 0.97)

    def test_untrusted_overrides_framework_proxy(self):
        # Defect D: cli.py used to blanket-downgrade eval to Low. Genuine taint
        # must override the filename proxy and the intentional-pattern framing.
        i = self._eval_issue("eval(request.args['q'])\n", file_path="cli.py")
        self.assertEqual(i["severity"], "Critical")
        self.assertNotIn("[Intentional Pattern]", i["description"])

    def test_operator_eval_downgrades_to_info(self):
        i = self._eval_issue("import sys\nx=sys.argv[1]\neval(x)\n", file_path="v.py")
        self.assertEqual(i["severity"], "Info")
        self.assertEqual(i["trust_boundary"], TRUST_OPERATOR)

    def test_confidence_is_reachability_derived(self):
        # Retires defect #3: confidence tracks trust tier, never the old flat 0.90.
        crit = self._eval_issue("eval(request.args['q'])\n", file_path="v.py")
        op = self._eval_issue("import sys\nx=sys.argv[1]\neval(x)\n", file_path="v.py")
        const = self._eval_issue("eval('1+1')\n", file_path="v.py")
        self.assertGreater(crit["confidence"], op["confidence"])
        self.assertGreater(op["confidence"], const["confidence"])
        self.assertNotIn(0.90, [crit["confidence"], op["confidence"], const["confidence"]])

    def test_command_injection_untrusted_is_critical(self):
        issues = detect_security_issues("import os\nos.system(request.args['c'])\n",
                                        file_path="views.py")
        cmd = [i for i in issues if i["type"] == "Command Injection"]
        self.assertEqual(len(cmd), 1)
        self.assertEqual(cmd[0]["severity"], "Critical")
        self.assertEqual(cmd[0]["trust_boundary"], TRUST_UNTRUSTED)

    # --- existing invariants that taint must NOT disturb ---

    def test_constant_eval_in_cli_still_low_intentional(self):
        # Phase C: still Low + intentional, but a cleared pattern is no longer
        # emitted as a finding — it is only visible under include_benign=True.
        # The invariant this guards is unchanged: a CONSTANT eval in a CLI must
        # not be escalated. test_untrusted_overrides_framework_proxy above is
        # the counterpart proving taint still overrides that framing.
        issues = detect_security_issues("eval('1 + 1')\n", file_path="cli.py")
        self.assertEqual([i for i in issues if i["type"] == "Dangerous Function"], [])

        cleared = detect_security_issues("eval('1 + 1')\n", file_path="cli.py",
                                         include_benign=True)
        dangerous = [i for i in cleared if i["type"] == "Dangerous Function"]
        self.assertEqual(len(dangerous), 1, cleared)
        self.assertEqual(dangerous[0]["severity"], "Low")
        self.assertIn("[Intentional Pattern]", dangerous[0]["description"])
        self.assertIn("CLI", dangerous[0]["description"])

    def test_safe_subprocess_list_still_low(self):
        issues = detect_security_issues("import subprocess\nsubprocess.run(['ls','-l'])\n",
                                        file_path="app.py")
        cmd = [i for i in issues if i["type"] == "Command Injection"]
        self.assertEqual(len(cmd), 1)
        self.assertEqual(cmd[0]["severity"], "Low")

    def test_every_issue_carries_trust_boundary(self):
        # The field must always be present for the UI, even for non-taint issues.
        issues = detect_security_issues("password = 'hunter2secret'\n", file_path="config.py")
        self.assertTrue(issues)
        for i in issues:
            self.assertIn("trust_boundary", i)


if __name__ == "__main__":
    unittest.main()
