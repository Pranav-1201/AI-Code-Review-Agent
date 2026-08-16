"""
command_injection precision (Phase C, final item).

thresholds.json carried `command_injection: {"precision": 0.66}` with the note
"over-flagging safe subprocess.run(list)" — a floor set at a known defect, which
by this project's own standing rule means the gate was ratifying the bug. The
labelled decoy is f2_security_injection/app.py:15, `subprocess.run(["ls", "-l"])`.

Investigating it turned up something worse than over-flagging. The classifier
branched on `isinstance(arg0, ast.List)` and returned

    'constant list args with shell=False — safe invocation pattern'

WITHOUT checking that the elements are constants. So

    subprocess.run(["sh", "-c", user])

— a live command injection through a function parameter — was described to the
reader as a *safe invocation pattern* at severity Low. The list is not constant.
Taint analysis saved the `request.args` case (it replaces the description
wholesale), but the parameter-level case fell straight through with contradictory
text: "safe invocation pattern" followed by "flows from an unvalidated parameter".

So the fix is not "stop reporting list calls". It is: decide whether the list is
actually constant, suppress only that case as benign (A2's mechanism), and route
a list holding dynamic elements to the dynamic-argument branch where it belongs.

These tests pin both directions — the FP that is now silent, and the finding that
must NOT go silent with it.
"""

import pytest

from backend.app.services.security_analyzer import detect_security_issues


def _cmd_findings(code, include_benign=False):
    issues = detect_security_issues(
        code, is_test_file=False, file_path="app.py", include_benign=include_benign
    )
    return [i for i in issues if "Command" in str(i.get("type", ""))]


# ----------------------------------------------------------
# The FP the gate was ratifying
# ----------------------------------------------------------

def test_all_constant_list_produces_no_finding():
    """The labelled decoy. A finding that says 'safe' is an FP by construction."""
    code = "import subprocess\ndef f():\n    subprocess.run(['ls', '-l'])\n"

    assert _cmd_findings(code) == []


def test_the_cleared_call_is_still_visible_as_benign():
    """Suppressed, not deleted — A2's contract for cleared findings."""
    code = "import subprocess\ndef f():\n    subprocess.run(['ls', '-l'])\n"

    benign = [i for i in _cmd_findings(code, include_benign=True) if i.get("benign")]

    assert len(benign) == 1


def test_constant_list_with_shell_true_is_still_reported():
    """shell=True on a list is redundant and risky — not the benign case."""
    code = "import subprocess\ndef f():\n    subprocess.run(['ls', '-l'], shell=True)\n"

    assert len(_cmd_findings(code)) == 1


# ----------------------------------------------------------
# The FN this uncovered — must not go quiet
# ----------------------------------------------------------

def test_dynamic_element_in_a_list_is_still_reported():
    code = "import subprocess\ndef f(user):\n    subprocess.run(['sh', '-c', user])\n"

    assert len(_cmd_findings(code)) == 1


def test_dynamic_element_is_never_described_as_safe():
    """The actual defect: the reader was told an injection vector was safe."""
    code = "import subprocess\ndef f(user):\n    subprocess.run(['sh', '-c', user])\n"

    description = _cmd_findings(code)[0]["description"]

    assert "safe" not in description.lower()
    assert "constant list" not in description.lower()


def test_dynamic_element_with_shell_true_is_high():
    code = ("import subprocess\ndef f(user):\n"
            "    subprocess.run(['sh', '-c', user], shell=True)\n")

    assert _cmd_findings(code)[0]["severity"] == "High"


def test_f_string_element_counts_as_dynamic():
    code = ("import subprocess\ndef f(user):\n"
            "    subprocess.run(['sh', '-c', f'echo {user}'])\n")

    assert len(_cmd_findings(code)) == 1


def test_nested_call_element_counts_as_dynamic():
    code = ("import subprocess\ndef f(user):\n"
            "    subprocess.run(['sh', '-c', user.strip()])\n")

    assert len(_cmd_findings(code)) == 1


# ----------------------------------------------------------
# Regression guards — suppression must not outrank taint,
# and the true positives must survive
# ----------------------------------------------------------

def test_untrusted_input_through_a_list_stays_critical():
    """A2's safety property: taint replaces the description before suppression."""
    code = ("import subprocess\nfrom flask import request\ndef f():\n"
            "    user = request.args.get('c')\n"
            "    subprocess.run(['sh', '-c', user])\n")

    findings = _cmd_findings(code)

    assert len(findings) == 1
    assert findings[0]["severity"] == "Critical"


def test_os_system_concat_is_still_reported():
    code = ("import os\ndef backup(path):\n"
            "    os.system('tar -czf backup.tgz ' + path)\n")

    assert len(_cmd_findings(code)) >= 1


def test_string_command_with_shell_true_is_still_reported():
    code = "import subprocess\ndef run_shell(cmd):\n    subprocess.call(cmd, shell=True)\n"

    assert len(_cmd_findings(code)) >= 1
