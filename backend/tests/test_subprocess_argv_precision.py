"""
Phase G / S3 -- list argv is safe by ARGV[0], not by being all-constant.

Phase C tightened the safe case to "every element is a literal", because
`["sh", "-c", user]` is a list, carries no shell=True, and is still a live
command injection -- describing it as safe was worse than over-reporting it.
That reasoning is correct and these tests keep it.

What it got wrong is the converse. Under shell=False the argv list is passed to
execve as-is, so no element after argv[0] can start a new command; it can only
ever be an argument to the program named in argv[0]. That makes the ordinary
Python idiom

    subprocess.run(["git", *args])
    subprocess.run(["git", "commit", "-m", message])
    cmd = ["git", "status"]; subprocess.run(cmd)

a false positive, and it is a very common one.

So the gate is argv[0], not element constancy: a list argv with shell not True
is safe when argv[0] is a constant that does not name a shell interpreter and
no -c style flag appears among the constant elements. `["sh", "-c", user]`
still fails that test, and so does `[user, "arg"]`, where the program itself is
attacker-chosen.

HANDOVER phrased this fix as "treat list argv with no shell as safe". Taken
literally that would have re-broken the Phase C case, so it is deliberately not
what is implemented here. See docs/DECISIONS.md.
"""

import pytest

from backend.app.services.security_analyzer import detect_security_issues


def _cmd_findings(code, include_benign=False):
    issues = detect_security_issues(
        code, is_test_file=False, file_path="app.py", include_benign=include_benign
    )
    return [i for i in issues if "Command" in str(i.get("type", ""))]


# ----------------------------------------------------------
# The false positives -- a real program with dynamic ARGUMENTS
# ----------------------------------------------------------

def test_starred_unpacking_into_argv_is_safe():
    code = "import subprocess\ndef f(args):\n    subprocess.run(['git', *args], shell=False)\n"

    assert _cmd_findings(code) == []


def test_starred_unpacking_without_explicit_shell_kwarg_is_safe():
    code = "import subprocess\ndef f(args):\n    subprocess.run(['git', *args])\n"

    assert _cmd_findings(code) == []


def test_dynamic_argument_to_a_real_program_is_safe():
    code = "import subprocess\ndef f(message):\n    subprocess.run(['git', 'commit', '-m', message])\n"

    assert _cmd_findings(code) == []


def test_list_held_in_a_local_variable_is_safe():
    code = (
        "import subprocess\ndef f():\n"
        "    cmd = ['git', 'status']\n"
        "    subprocess.run(cmd)\n"
    )

    assert _cmd_findings(code) == []


def test_absolute_path_to_a_real_program_is_safe():
    code = "import subprocess\ndef f(args):\n    subprocess.run(['/usr/bin/git', *args])\n"

    assert _cmd_findings(code) == []


def test_a_cleared_argv_call_is_still_visible_as_benign():
    """Suppressed, not deleted -- the reasoning stays inspectable."""
    code = "import subprocess\ndef f(args):\n    subprocess.run(['git', *args])\n"

    benign = [i for i in _cmd_findings(code, include_benign=True) if i.get("benign")]

    assert len(benign) == 1


# ----------------------------------------------------------
# argv[0] names a shell -- the Phase C case, must NOT go quiet
# ----------------------------------------------------------

def test_sh_dash_c_is_still_reported():
    code = "import subprocess\ndef f(user):\n    subprocess.run(['sh', '-c', user])\n"

    assert len(_cmd_findings(code)) == 1


def test_bash_dash_c_is_still_reported():
    code = "import subprocess\ndef f(user):\n    subprocess.run(['bash', '-c', user])\n"

    assert len(_cmd_findings(code)) == 1


def test_absolute_path_to_a_shell_is_still_reported():
    code = "import subprocess\ndef f(user):\n    subprocess.run(['/bin/sh', '-c', user])\n"

    assert len(_cmd_findings(code)) == 1


def test_windows_cmd_is_still_reported():
    code = "import subprocess\ndef f(user):\n    subprocess.run(['cmd', '/c', user])\n"

    assert len(_cmd_findings(code)) == 1


def test_powershell_is_still_reported():
    code = "import subprocess\ndef f(user):\n    subprocess.run(['powershell', '-Command', user])\n"

    assert len(_cmd_findings(code)) == 1


def test_shell_argv_in_a_local_variable_is_still_reported():
    code = (
        "import subprocess\ndef f(user):\n"
        "    cmd = ['sh', '-c', user]\n"
        "    subprocess.run(cmd)\n"
    )

    assert len(_cmd_findings(code)) == 1


# ----------------------------------------------------------
# argv[0] is attacker-chosen, or shell=True is set
# ----------------------------------------------------------

def test_dynamic_program_name_is_still_reported():
    """argv[0] itself is the variable -- the attacker picks the program."""
    code = "import subprocess\ndef f(prog):\n    subprocess.run([prog, 'arg'])\n"

    assert len(_cmd_findings(code)) == 1


def test_safe_argv_with_shell_true_is_still_reported():
    code = "import subprocess\ndef f(args):\n    subprocess.run(['git', *args], shell=True)\n"

    assert len(_cmd_findings(code)) == 1


def test_rebound_list_variable_is_not_treated_as_safe():
    """Two bindings -- which one reaches the call is not decidable here."""
    code = (
        "import subprocess\ndef f(user, flag):\n"
        "    cmd = ['git', 'status']\n"
        "    cmd = ['sh', '-c', user]\n"
        "    subprocess.run(cmd)\n"
    )

    assert len(_cmd_findings(code)) == 1


def test_untrusted_input_through_safe_argv_is_still_escalated():
    """Taint outranks the argv[0] clearance, as it outranks every clearance."""
    code = (
        "import subprocess\nfrom flask import request\ndef f():\n"
        "    user = request.args.get('c')\n"
        "    subprocess.run(['sh', '-c', user])\n"
    )

    findings = _cmd_findings(code)

    assert len(findings) == 1
    assert findings[0]["severity"] == "Critical"
