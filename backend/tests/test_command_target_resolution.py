"""
Phase G / S1 — the Command Injection detector must resolve the call TARGET.

Measured defect: `visit_Call` branched on the bare attribute name. `attr ==
"system"` and `attr in {"Popen", "call", "run"}` were checked against
`node.func.attr` with no look at `node.func.value` at all. So every one of these
was reported as Command Injection:

    app.run(debug=True)        # Flask — the single most common line in a Flask app
    self.run(a, b)             # any class with a run() method, e.g. a Celery task
    scheduler.run()            # sched, APScheduler, unittest TextTestRunner...

This is the largest single false-positive class the analyzer has. On
`pallets/flask` it accounted for findings that were 100% wrong
(docs/ANALYZER_ACCURACY_2026-08.md).

The fix resolves the receiver: `subprocess.run` fires, `app.run` does not.
Aliases (`import subprocess as sp`) and from-imports (`from subprocess import
run`) resolve too, so tightening the target does not open a recall hole.

These tests pin both directions — the FPs that must go silent, and every true
positive that must NOT go silent with them.
"""

import pytest

from backend.app.services.security_analyzer import detect_security_issues


def _cmd_findings(code):
    issues = detect_security_issues(code, is_test_file=False, file_path="app.py")
    return [i for i in issues if "Command" in str(i.get("type", ""))]


# ----------------------------------------------------------
# The false positives — a `run`/`system` on a non-subprocess receiver
# ----------------------------------------------------------

def test_flask_app_run_is_not_command_injection():
    code = (
        "from flask import Flask\n"
        "app = Flask(__name__)\n"
        "app.run(debug=True)\n"
    )

    assert _cmd_findings(code) == []


def test_self_run_is_not_command_injection():
    code = (
        "class Task:\n"
        "    def go(self):\n"
        "        self.run(1, 2)\n"
    )

    assert _cmd_findings(code) == []


def test_arbitrary_object_run_is_not_command_injection():
    code = (
        "def main(scheduler, cmd):\n"
        "    scheduler.run(cmd)\n"
    )

    assert _cmd_findings(code) == []


def test_arbitrary_object_call_is_not_command_injection():
    code = (
        "def main(handler, payload):\n"
        "    handler.call(payload)\n"
    )

    assert _cmd_findings(code) == []


def test_non_os_system_is_not_command_injection():
    """`.system` on anything that is not the os module."""
    code = (
        "def configure(manager, name):\n"
        "    manager.system(name)\n"
    )

    assert _cmd_findings(code) == []


# ----------------------------------------------------------
# The true positives that must survive the tightening
# ----------------------------------------------------------

def test_subprocess_run_still_reported():
    code = "import subprocess\ndef f(cmd):\n    subprocess.run(cmd, shell=True)\n"

    assert len(_cmd_findings(code)) >= 1


def test_subprocess_popen_still_reported():
    code = "import subprocess\ndef f(cmd):\n    subprocess.Popen(cmd, shell=True)\n"

    assert len(_cmd_findings(code)) >= 1


def test_os_system_still_reported():
    code = "import os\ndef f(path):\n    os.system('tar -czf b.tgz ' + path)\n"

    assert len(_cmd_findings(code)) >= 1


def test_aliased_subprocess_import_still_reported():
    code = "import subprocess as sp\ndef f(cmd):\n    sp.run(cmd, shell=True)\n"

    assert len(_cmd_findings(code)) >= 1


def test_aliased_os_import_still_reported():
    code = "import os as operating\ndef f(p):\n    operating.system('rm ' + p)\n"

    assert len(_cmd_findings(code)) >= 1


def test_from_import_of_subprocess_run_is_reported():
    """`from subprocess import run` — a bare Name call, still a subprocess call."""
    code = "from subprocess import run\ndef f(cmd):\n    run(cmd, shell=True)\n"

    assert len(_cmd_findings(code)) >= 1


def test_from_import_of_os_system_is_reported():
    code = "from os import system\ndef f(p):\n    system('rm ' + p)\n"

    assert len(_cmd_findings(code)) >= 1


def test_from_import_alias_is_reported():
    code = "from subprocess import run as launch\ndef f(cmd):\n    launch(cmd, shell=True)\n"

    assert len(_cmd_findings(code)) >= 1


def test_a_local_run_shadowing_an_import_is_not_confused():
    """No `from subprocess import run` here, so a bare `run()` is not subprocess."""
    code = "def run(x):\n    return x\ndef f(cmd):\n    run(cmd)\n"

    assert _cmd_findings(code) == []
