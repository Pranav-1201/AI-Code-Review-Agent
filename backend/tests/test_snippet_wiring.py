"""The two producers that used to emit a placeholder now emit real source.

`docs/HANDOVER.md` records the rule these tests exist to satisfy: a fixture
that passes both before and after a change is measuring nothing. Step 2 of
this task runs these against the unmodified analyzer and they must fail.
"""

import re
from unittest.mock import patch

from backend.app.analysis.taint_analyzer import InterProcFinding
from backend.app.services.repository_review_engine import apply_interprocedural_taint
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


def test_form_feed_above_the_finding_does_not_misalign_the_snippet():
    # \x0c (form feed) is a line boundary for str.splitlines() but NOT for
    # Python's tokenizer/AST — the AST lineno counts "\n" only. A source-line
    # array built with splitlines() therefore drifts by one row here, and the
    # snippet prints the WRONG line of code under the (correct) AST line
    # number.
    src = ('import subprocess\n\x0c\ndef handler(request):\n'
           '    cmd = request.args.get("cmd")\n'
           '    subprocess.run(cmd, shell=True)\n')
    issues = _security_issues(src)
    assert issues, "expected a finding on this source"

    finding = issues[0]
    line = finding["line"]
    snippet = finding["snippet"]

    numbered = {}
    for row in snippet.split("\n"):
        number, _, text = row.partition(": ")
        numbered[int(number)] = text

    assert "subprocess.run" in numbered.get(line, ""), (
        f"line {line} should show the flagged call, got {numbered.get(line)!r} "
        f"(full snippet: {snippet!r})"
    )


# ----------------------------------------------------------------------
# The second producer: apply_interprocedural_taint (repository_review_engine.py)
# escalates sinks that Phase-4 inter-procedural taint proves are reachable
# from untrusted input across a call chain. It had no test at all before
# this: the two shapes below match what review_repository actually builds
# (analyze_single_file's per-file result at repository_review_engine.py:245-264,
# fed to apply_interprocedural_taint at line 439) and drive it directly, the
# way _security_issues() above drives the per-file analyzer directly.
# ----------------------------------------------------------------------

# Proven to produce a cross-function os.system finding by
# TestInterproceduralTaint.test_untrusted_arg_into_param_sink in
# test_architecture.py: `view` passes attacker-controlled `request.args['c']`
# into `run`, where it reaches the sink — the taint crosses a function
# boundary, which is exactly what apply_interprocedural_taint escalates.
CROSS_FUNCTION_TAINT = ("import os\n"
                        "def run(cmd):\n"
                        "    os.system(cmd)\n"
                        "\n"
                        "def view():\n"
                        "    run(request.args['c'])\n")


def test_interprocedural_finding_carries_the_source_that_triggered_it():
    results = [{"file_path": "w.py", "content": CROSS_FUNCTION_TAINT,
                "security_risks": [], "issues": []}]

    apply_interprocedural_taint(results)

    risks = results[0]["security_risks"]
    assert risks, "expected the interprocedural pass to escalate the os.system sink"

    snippet = risks[0]["snippet"]
    assert "os.system" in snippet
    assert re.match(r"^\d+: ", snippet), f"not line-numbered: {snippet!r}"
    assert not LEGACY.match(snippet), f"still the placeholder shape: {snippet!r}"

    # The issue-explorer copy is kept in sync with the security_risks entry
    # (repository_review_engine.py:361-369) and must carry the same evidence.
    issue_snippet = results[0]["issues"][0]["snippet"]
    assert issue_snippet == snippet


def test_interprocedural_finding_empty_snippet_when_source_unavailable():
    # apply_interprocedural_taint builds its own `sources` map from each
    # result's `content` and looks a finding's file up in that map, falling
    # back to "" when absent (repository_review_engine.py:306-321). Under
    # the real call path this can't be hit organically: findings only ever
    # name a file that propagate_interprocedural_taint was given content
    # for, since that's the same `sources` dict. So this stubs the taint
    # pass's return value to name a file whose content is empty ("" is
    # filtered out of `sources` the same as absent) and drives the rest of
    # apply_interprocedural_taint's real logic — the snippet computation
    # this test exists for.
    finding = InterProcFinding(
        sink_name="os.system", category="command", file="w.py", line=3,
        source_kind="web_request", callee="w::run",
        trust_boundary="untrusted_input", confidence=0.85,
    )
    results = [{"file_path": "w.py", "content": "", "security_risks": [], "issues": []}]

    with patch(
        "backend.app.services.repository_review_engine.propagate_interprocedural_taint",
        return_value=[finding],
    ):
        apply_interprocedural_taint(results)

    assert results[0]["security_risks"][0]["snippet"] == ""
    assert results[0]["issues"][0]["snippet"] == ""
