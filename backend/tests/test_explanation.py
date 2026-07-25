"""
Phase 5 tests for the Anthropic explanation layer. The LLM stays gated OFF
(no env), so these exercise the deterministic-fallback + prompt-construction
paths only — no network, fully deterministic.
"""

import os
import unittest

os.environ.pop("ENABLE_ANTHROPIC", None)
os.environ.pop("ANTHROPIC_API_KEY", None)

from backend.app.services import explanation_engine as EE


class TestGating(unittest.TestCase):
    def test_unavailable_without_env(self):
        self.assertFalse(EE.anthropic_available())

    def test_gated_off_returns_fallback_verbatim(self):
        res = EE.generate_explanation({"file_name": "x.py"}, "FALLBACK", depth="senior")
        self.assertEqual(res["source"], "deterministic")
        self.assertEqual(res["text"], "FALLBACK")
        self.assertIsNone(res["model"])


class TestGrounding(unittest.TestCase):
    EV = {
        "file_name": "views.py", "language": "python",
        "complexity": {"cyclomatic_complexity": 4, "max_loop_depth": 1},
        "quality_score": 70,
        "security_findings": [{
            "type": "Dangerous Function", "severity": "Critical",
            "description": "eval reachable from request.args",
            "trust_boundary": "untrusted_input"}],
    }

    def test_evidence_is_in_prompt(self):
        msgs = EE._build_messages(self.EV, "senior")
        self.assertIn("untrusted_input", msgs["user"])
        self.assertIn("eval reachable from request.args", msgs["user"])
        self.assertIn("views.py", msgs["user"])

    def test_anti_hallucination_rules_present(self):
        system = EE._build_messages(self.EV, "senior")["system"]
        self.assertIn("Do not invent", system)
        self.assertIn("do not contradict", system.lower())

    def test_no_findings_message(self):
        msgs = EE._build_messages({"file_name": "clean.py"}, "senior")
        self.assertIn("No security or structural findings", msgs["user"])


class TestDepthToggle(unittest.TestCase):
    def test_junior_vs_senior(self):
        ev = {"file_name": "v.py"}
        self.assertIn("JUNIOR", EE._build_messages(ev, "junior")["system"])
        self.assertIn("SENIOR", EE._build_messages(ev, "senior")["system"])

    def test_invalid_depth_defaults_senior(self):
        self.assertIn("SENIOR", EE._build_messages({"file_name": "v.py"}, "wizard")["system"])


if __name__ == "__main__":
    unittest.main()
