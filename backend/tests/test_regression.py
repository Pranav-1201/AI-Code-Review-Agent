"""
Regression tests for complexity, security, and scoring edge cases.
Covers the accuracy fixes from the Flask cross-analysis.

Ported to the current API (Chunk 0):
  - `_heuristic_analysis` and `compute_quality_score` take a
    complexity DICT ({"max_loop_depth": int, "cyclomatic_complexity": int}),
    not a legacy "O(...)" string.
  - `compute_quality_score` returns a (score, breakdown) tuple.
  - the missing-__main__-guard heuristic is role-gated: it fires only for
    non-library roles (e.g. cli_parser), so the "regular file" case passes
    an applicable file_role explicitly.
"""

import unittest
import ast
from backend.app.services.security_analyzer import detect_security_issues
from backend.app.services.llm_service import _heuristic_analysis
from backend.app.services.quality_scorer import compute_quality_score
from backend.app.analysis.complexity_analyzer import ComplexityAnalyzer


# Complexity dicts replacing the old "O(...)" strings
CX_O1 = {"cyclomatic_complexity": 1, "max_loop_depth": 0}
CX_ON2 = {"cyclomatic_complexity": 12, "max_loop_depth": 2}


class TestSecurityRegression(unittest.TestCase):
    """Fix 7: Context-aware security reasoning."""

    def test_mock_credential_in_test_file_ignored(self):
        code = "SECRET_KEY = 'test_mock_value'\n"
        issues = detect_security_issues(code, is_test_file=True, file_path="test_config.py")
        self.assertEqual(len(issues), 0, "Should not flag credentials in test files")

    def test_mock_credential_in_prod_file_flagged(self):
        code = "SECRET_KEY = 'real_prod_secret'\n"
        issues = detect_security_issues(code, is_test_file=False, file_path="config.py")
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["type"], "Hardcoded Credential")

    # Phase C note: these two still assert that the analyzer REASONS about
    # framework context and says WHY a pattern is intentional — the original
    # point of Fix 7. What changed is where that reasoning lands. A cleared
    # finding is no longer emitted into the user's security findings list (it
    # was counted, correctly, as a false positive by the benchmark); it is
    # returned only under include_benign=True. See
    # test_benign_pattern_suppression.py.

    def test_eval_in_framework_context_has_reasoning(self):
        code = "eval('1 + 1')\n"
        issues = detect_security_issues(code, is_test_file=False, file_path="cli.py")
        self.assertEqual(issues, [], "a cleared pattern must not be a finding")

        cleared = detect_security_issues(code, is_test_file=False,
                                         file_path="cli.py", include_benign=True)
        self.assertEqual(len(cleared), 1)
        self.assertEqual(cleared[0]["severity"], "Low")
        self.assertIn("[Intentional Pattern]", cleared[0]["description"])
        # Fix 7: must contain WHY it's intentional
        self.assertIn("CLI", cleared[0]["description"])

    def test_exec_in_config_has_reasoning(self):
        code = "exec(compile(f.read(), 'config', 'exec'))\n"
        issues = detect_security_issues(code, is_test_file=False, file_path="config.py")
        self.assertEqual(issues, [], "a cleared pattern must not be a finding")

        cleared = detect_security_issues(code, is_test_file=False,
                                         file_path="config.py", include_benign=True)
        exec_issues = [i for i in cleared if "exec()" in i["description"]]
        self.assertTrue(len(exec_issues) >= 1)
        self.assertIn("config file loading", exec_issues[0]["description"])

    def test_subprocess_with_constants(self):
        code = "import subprocess\nsubprocess.run(['ls', '-l'])\n"
        issues = detect_security_issues(code, is_test_file=False, file_path="app.py")
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["severity"], "Low")


class TestComplexityRegression(unittest.TestCase):
    """Fix 1: Comprehension-as-loop inflation."""

    def test_comprehension_inside_loop_is_not_nested(self):
        """A list comprehension inside a for loop should NOT inflate
        nesting depth. This was the root cause of logging.py getting O(n²)."""
        code = '''
def has_level_handler(logger):
    while logger:
        result = [h for h in logger.handlers if h.level]
        logger = logger.parent
    return False
'''
        tree = ast.parse(code)
        analyzer = ComplexityAnalyzer()
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                metrics = analyzer.analyze_function(node)
                # Should be depth 1 (just the while loop), NOT depth 2
                self.assertEqual(metrics["max_loop_depth"], 1,
                    "Comprehension inside a loop should not count as nesting")
                self.assertEqual(metrics["time_complexity"], "O(n)")

    def test_actual_nested_loops_still_detected(self):
        code = '''
def nested():
    for x in range(10):
        for y in range(5):
            pass
'''
        tree = ast.parse(code)
        analyzer = ComplexityAnalyzer()
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                metrics = analyzer.analyze_function(node)
                self.assertEqual(metrics["max_loop_depth"], 2)
                self.assertEqual(metrics["time_complexity"], "O(n^2)")

    def test_sequential_loops_are_not_nested(self):
        code = '''
def sequential():
    for x in range(10):
        pass
    for y in range(5):
        pass
'''
        tree = ast.parse(code)
        analyzer = ComplexityAnalyzer()
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                metrics = analyzer.analyze_function(node)
                self.assertEqual(metrics["max_loop_depth"], 1,
                    "Sequential loops should not count as nested")


class TestMainGuardRegression(unittest.TestCase):
    """Fix 3: __main__.py should never be flagged for missing guard."""

    def test_main_module_no_guard_warning(self):
        code = "from .cli import main\nmain()\n"
        issues = _heuristic_analysis(code, complexity=CX_O1, filename="__main__.py")
        guard_issues = [i for i in issues if "__name__" in i.get("message", "")]
        self.assertEqual(len(guard_issues), 0,
            "__main__.py should never be flagged for missing if __name__ guard")

    def test_regular_file_still_flagged(self):
        # The guard heuristic is role-gated (Defect C): it is suppressed for
        # library roles (utility/data_model/orchestrator). A CLI entry point is
        # exactly where it should still fire, so pass file_role='cli_parser'.
        code = "app.run()\n"
        issues = _heuristic_analysis(code, complexity=CX_O1, filename="server.py",
                                     file_role="cli_parser")
        guard_issues = [i for i in issues if "__name__" in i.get("message", "")]
        self.assertEqual(len(guard_issues), 1,
            "An applicable file with top-level execution should still be flagged")


class TestSizeFlagRegression(unittest.TestCase):
    """Phase 2: size flagging is cohesion-gated (line_count > 500 AND
    module_cohesion < 0.40), replacing the old flat line-count rule. The
    Fix-4 guarantee is carried forward: when the warning fires, it reports
    the TOTAL line count, not the stripped count.

    (Was TestLineCountRegression; the old test asserted a 350-line file is
    flagged, which the cohesion gate deliberately no longer does.)"""

    def test_large_low_cohesion_file_flagged_with_total_line_count(self):
        # 8 top-level functions that share nothing -> cohesion 0.0.
        # Padded past the 500-line gate with BLANK lines, so the total line
        # count is far larger than the non-blank count.
        funcs = "".join(f"def f{i}(a{i}):\n    return a{i}\n\n" for i in range(8))
        code = funcs + ("\n" * 520)
        total = len(code.splitlines())
        issues = _heuristic_analysis(code, complexity=CX_O1, filename="tangled.py")
        size_issues = [i for i in issues if "cohesion" in i.get("message", "").lower()]
        self.assertEqual(len(size_issues), 1, "large low-cohesion file must be flagged")
        self.assertIn(str(total), size_issues[0]["message"],
            "warning must report the TOTAL line count, not the stripped count")

    def test_large_cohesive_file_not_flagged(self):
        # Same size, but every function shares `registry` -> high cohesion.
        # This is the Flask sessions.py regression: long but cohesive == fine.
        funcs = "".join(
            f"def f{i}(registry):\n    registry.append({i})\n    return registry\n\n"
            for i in range(8))
        code = funcs + ("\n" * 520)
        issues = _heuristic_analysis(code, complexity=CX_O1, filename="cohesive.py")
        size_issues = [i for i in issues if "cohesion" in i.get("message", "").lower()]
        self.assertEqual(len(size_issues), 0,
            "a long but cohesive file must NOT be flagged")


class TestScoringRegression(unittest.TestCase):
    """Fix 2: Clean small files should score 88+, not cap at 81."""

    def test_clean_file_scores_above_88(self):
        # Clean, trivial file with moderate AI probability
        score, _ = compute_quality_score(
            issue_probability=0.5,
            complexity=CX_O1,
            security_issues=[],
            is_test_file=False
        )
        self.assertGreaterEqual(score, 88,
            f"Clean O(1) file with no security issues should score >= 88, got {score}")

    def test_complex_file_still_penalized(self):
        score, _ = compute_quality_score(
            issue_probability=0.5,
            complexity=CX_ON2,
            security_issues=[{"severity": "Medium", "type": "Dangerous Function"}],
            is_test_file=False
        )
        self.assertLess(score, 88,
            f"Complex file with security issues should score < 88, got {score}")

    def test_info_severity_no_penalty(self):
        # Assert the intent directly via the breakdown: an Info-severity issue
        # contributes ZERO security penalty (comparing raw scores is confounded
        # by the clean-file bonus, which is gated on issue COUNT, not penalty).
        _, bd_clean = compute_quality_score(0.3, CX_O1, [], is_test_file=False)
        _, bd_info = compute_quality_score(
            0.3, CX_O1, [{"severity": "Info", "type": "test"}], is_test_file=False)
        _, bd_low = compute_quality_score(
            0.3, CX_O1, [{"severity": "Low", "type": "test"}], is_test_file=False)
        self.assertEqual(bd_info["security"], 0,
            "Info-level issues should carry zero security penalty")
        self.assertEqual(bd_clean["security"], 0)
        self.assertLess(bd_low["security"], 0,
            "A Low-severity issue must still carry a (non-zero) penalty")


class TestHeuristicComplexityInput(unittest.TestCase):
    """Fix 5: Heuristic should use passed complexity, not recalculate."""

    def test_heuristic_uses_complexity_param(self):
        """Even if the code has no loops, passing a depth-2 complexity dict
        should generate a performance issue (heuristic trusts the param)."""
        code = "x = 1\ny = 2\n"
        issues = _heuristic_analysis(code, complexity={"max_loop_depth": 2,
                                                       "cyclomatic_complexity": 1})
        perf_issues = [i for i in issues if i.get("type") == "performance"]
        self.assertEqual(len(perf_issues), 1)
        self.assertIn("Nested loop", perf_issues[0]["message"])

    def test_heuristic_o1_no_perf_issue(self):
        code = "x = 1\n"
        issues = _heuristic_analysis(code, complexity=CX_O1)
        perf_issues = [i for i in issues if i.get("type") == "performance"]
        self.assertEqual(len(perf_issues), 0)


if __name__ == "__main__":
    unittest.main()
