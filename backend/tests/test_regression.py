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

    def test_eval_in_framework_context_has_reasoning(self):
        code = "eval('1 + 1')\n"
        issues = detect_security_issues(code, is_test_file=False, file_path="cli.py")
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["severity"], "Low")
        self.assertIn("[Intentional Pattern]", issues[0]["description"])
        # Fix 7: must contain WHY it's intentional
        self.assertIn("CLI", issues[0]["description"])

    def test_exec_in_config_has_reasoning(self):
        code = "exec(compile(f.read(), 'config', 'exec'))\n"
        issues = detect_security_issues(code, is_test_file=False, file_path="config.py")
        exec_issues = [i for i in issues if "exec()" in i["description"]]
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


class TestLineCountRegression(unittest.TestCase):
    """Fix 4: Line count should use total lines, not stripped."""

    def test_total_lines_in_file_length_message(self):
        # 350 total lines (including blanks), but only ~175 non-blank
        code = ("x = 1\n\n") * 175  # 350 lines total
        issues = _heuristic_analysis(code, complexity=CX_O1)
        length_issues = [i for i in issues if "lines" in i.get("message", "")]
        self.assertTrue(len(length_issues) >= 1, "Should flag a 350-line file")
        self.assertIn("350", length_issues[0]["message"],
            "Should report total line count, not stripped count")


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
