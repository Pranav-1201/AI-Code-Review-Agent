"""
Benign-pattern suppression (Phase C / roadmap A2).

The real-repo benchmark sat at precision 0.46 with 7 false positives. Probing
each one showed the analyzer was not confused — it had already worked out that
three of them were safe and reported them anyway:

  flask/sessions.py:285  Info  "SHA-1 in HMAC context - computationally
                               secure for message signing"
  flask/cli.py:1005      Info  "[Intentional Pattern] compile() in CLI startup"
  flask/config.py:212    Low   "[Intentional Pattern] exec() in config file
                               loading - executes Python config files from a
                               trusted path"

A security findings list that contains an entry saying "this is secure" is a
false positive by construction: it costs the reader the same attention as a
real vulnerability and then tells them there is nothing there. The analyzer's
own verdict is the fix — findings it positively determines to be benign are
withheld from the findings list rather than emitted at low severity.

SAFETY PROPERTY these tests pin: the "[Intentional Pattern]" framing is applied
from a filename heuristic, but _apply_taint REPLACES that framing outright when
a sink is reachable from untrusted input (security_analyzer._apply_taint,
TRUST_UNTRUSTED branch). So suppression can never hide a tainted sink — the
marker is gone by the time the finding is built. If that ordering is ever
broken, test_untrusted_input_still_reported_in_framework_file fails.
"""

import pytest

from backend.app.services.security_analyzer import detect_security_issues


def _types(issues):
    return [i["type"] for i in issues]


# ----------------------------------------------------------
# Suppressed: the analyzer said it was safe
# ----------------------------------------------------------

def test_sha1_in_hmac_context_is_not_a_finding():
    """SHA-1 under HMAC is a correct construction, not a weak hash.

    Would fail if: the hmac-context verdict goes back to being emitted, which
    is one of the two weak_crypto false positives on flask.
    """
    code = (
        "import hmac, hashlib\n"
        "def sign(key, msg):\n"
        "    return hmac.new(key, msg, hashlib.sha1).hexdigest()\n"
    )
    issues = detect_security_issues(code, file_path="sessions.py")
    assert not [i for i in issues if "Crypt" in i["type"]], issues


def test_intentional_framework_pattern_is_not_a_finding():
    """exec() of a developer's own config file is a documented feature.

    Would fail if: findings the analyzer labels "[Intentional Pattern]" are
    emitted again — two of the five dangerous_function false positives.
    """
    code = (
        "def from_pyfile(filename):\n"
        "    d = {}\n"
        "    with open(filename) as f:\n"
        "        exec(compile(f.read(), filename, 'exec'), d)\n"
        "    return d\n"
    )
    issues = detect_security_issues(code, file_path="config.py")
    assert not [i for i in issues if "Dangerous" in i["type"]], issues


# ----------------------------------------------------------
# NOT suppressed: everything the analyzer has not cleared
# ----------------------------------------------------------

def test_untrusted_input_still_reported_in_framework_file():
    """Taint outranks the filename heuristic — this is the safety property.

    eval() on request data inside a file named config.py must stay Critical.
    Suppression keys on a marker that _apply_taint strips for untrusted sinks,
    so the two cannot collide; this test is what proves that ordering holds.

    Would fail if: suppression is moved ahead of the taint overlay, or keyed on
    the filename instead of the analyzer's post-taint verdict — either of which
    would silently hide real RCE in any file called config.py or app.py.
    """
    code = (
        "from flask import request\n"
        "def handler():\n"
        "    return eval(request.args['q'])\n"
    )
    issues = detect_security_issues(code, file_path="config.py")
    dangerous = [i for i in issues if "Dangerous" in i["type"]]
    assert dangerous, "untrusted eval() was suppressed by the framework heuristic"
    assert any(i["severity"] == "Critical" for i in dangerous), dangerous


@pytest.mark.parametrize("filename", ["app.py", "__init__.py", "loader.py",
                                      "runner.py", "commands.py", "factory.py"])
def test_ordinary_filenames_are_not_trusted_contexts(filename):
    """A file being called app.py does not make exec() intentional.

    The framework heuristic originally matched app.py, __init__.py, factory,
    loader, runner and commands — some of the most common names in Python. Every
    eval/exec in such a file was reframed as an "[Intentional Pattern]", which
    was survivable only while those findings were still emitted at low severity.
    Once benign patterns stopped being reported it became a silent miss, and the
    benchmark caught it immediately: dangerous_function fixture recall fell from
    1.00 to 0.00, because that fixture's planted true positives live in app.py.

    Would fail if: the trusted-context list is widened back towards ordinary
    filenames, which turns every eval() in an app.py into a false negative.
    """
    code = "def run(src):\n    return eval(src)\n"
    issues = detect_security_issues(code, file_path=filename)
    assert [i for i in issues if "Dangerous" in i["type"]], (
        f"eval() in {filename} was silently cleared as a framework pattern")


def test_bare_sha1_is_still_reported():
    """SHA-1 outside a cleared context keeps its finding."""
    code = "import hashlib\ndef h(d):\n    return hashlib.sha1(d).hexdigest()\n"
    issues = detect_security_issues(code, file_path="util.py")
    assert [i for i in issues if "Crypt" in i["type"]], issues


def test_plain_exec_is_still_reported():
    """exec() in an ordinary module is not an intentional pattern."""
    code = "def run(src):\n    exec(src)\n"
    issues = detect_security_issues(code, file_path="worker.py")
    assert [i for i in issues if "Dangerous" in i["type"]], issues


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
