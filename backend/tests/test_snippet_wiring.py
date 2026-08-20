"""The two producers that used to emit a placeholder now emit real source.

`docs/HANDOVER.md` records the rule these tests exist to satisfy: a fixture
that passes both before and after a change is measuring nothing. Step 2 of
this task runs these against the unmodified analyzer and they must fail.
"""

import re

from backend.app.services.security_analyzer import (
    SecurityAnalyzer,
    detect_security_issues,
)

LEGACY = re.compile(r"^Line \d+( indicates: .+)?$")

VULNERABLE = '''import subprocess


def handler(request):
    cmd = request.args.get("cmd")
    subprocess.run(cmd, shell=True)
'''


def _security_issues(source: str, path: str = "app/handler.py"):
    # detect_security_issues is the real entry point (see
    # repository_review_engine.py:15) — it parses, builds the symbol table
    # and taint map, binds imports, and walks the tree. Driving the analyzer
    # any other way risks testing plumbing the product never runs.
    return detect_security_issues(source, file_path=path)


def test_a_finding_carries_the_source_that_triggered_it():
    issues = _security_issues(VULNERABLE)
    assert issues, "expected at least one security finding on this source"

    snippet = issues[0]["snippet"]

    assert "subprocess.run" in snippet
    assert not LEGACY.match(snippet), f"still the placeholder shape: {snippet!r}"


def test_the_snippet_is_line_numbered():
    issues = _security_issues(VULNERABLE)

    snippet = issues[0]["snippet"]

    assert re.match(r"^\d+: ", snippet), f"not line-numbered: {snippet!r}"


def test_no_source_yields_an_empty_snippet_not_a_sentence():
    # The analyzer is constructible without source; findings from that path
    # must say nothing rather than restate their own line number.
    analyzer = SecurityAnalyzer(file_path="app/handler.py", source="")
    analyzer._add_issue("High", "Something", "Fix it", line=12, issue_type="Command Injection")

    assert analyzer.issues[0]["snippet"] == ""
