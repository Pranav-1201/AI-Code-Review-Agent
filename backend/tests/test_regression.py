import unittest
import ast
from backend.app.services.security_analyzer import detect_security_issues
from backend.app.services.llm_service import _heuristic_analysis

class TestRegression(unittest.TestCase):
    
    def test_mock_credential_in_test_file_ignored(self):
        code = "SECRET_KEY = 'test_mock_value'\n"
        # In a test file, it should NOT flag Hardcoded Credential
        issues = detect_security_issues(code, is_test_file=True, file_path="test_config.py")
        self.assertEqual(len(issues), 0, "Should not flag credentials in test files")

    def test_mock_credential_in_prod_file_flagged(self):
        code = "SECRET_KEY = 'real_prod_secret'\n"
        # In a generic prod file, it SHOULD flag Hardcoded Credential
        issues = detect_security_issues(code, is_test_file=False, file_path="config.py")
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["type"], "Hardcoded Credential")

    def test_eval_in_framework_context(self):
        code = "eval('1 + 1')\n"
        issues = detect_security_issues(code, is_test_file=False, file_path="cli.py")
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["severity"], "Low")
        self.assertIn("Intentional Pattern", issues[0]["description"])

    def test_subprocess_with_constants(self):
        code = "import subprocess\nsubprocess.run(['ls', '-l'])\n"
        issues = detect_security_issues(code, is_test_file=False, file_path="app.py")
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["severity"], "Low", "Subprocess with strict list constants is Low risk")
        self.assertIn("[Verify Context]", issues[0]["description"])

    def test_heuristic_analysis_nesting(self):
        # 1 flat loop, 1 flat loop (no nesting)
        code = '''
for x in range(10): pass
while True: pass
        '''
        issues, complexity = _heuristic_analysis(code)
        self.assertNotIn("Nested loop", str(issues))

    def test_heuristic_analysis_deep_nesting(self):
        # Nested depth 3
        code = '''
for x in range(10):
    for y in range(5):
        while z:
            pass
        '''
        issues, complexity = _heuristic_analysis(code)
        self.assertEqual(complexity, "O(n³)")
        performance_issues = [i for i in issues if i.get("type", "") == "performance"]
        self.assertTrue(any("Deeply nested" in i["message"] for i in performance_issues))

if __name__ == "__main__":
    unittest.main()
