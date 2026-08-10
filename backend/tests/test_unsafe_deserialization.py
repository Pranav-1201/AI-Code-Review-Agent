"""
Unsafe-deserialization sink coverage (Phase C / roadmap A1).

The benchmark recorded unsafe_deserialization at recall 0.33 — one of three
planted true positives found — and thresholds.json recorded the floor as 0.33,
so the release gate was *enforcing* the bug rather than catching it. A gate that
ratifies a known miss is worse than no gate for that type.

Root cause: the detector matched `attr == "loads"` only, so `pickle.load(fp)`
and `yaml.load(text)` both walked past it. The yaml branch was additionally
nested inside that plural-only check while PyYAML exposes no `yaml.loads` at
all, making it unreachable on any real code.

These tests pin each sink independently so a future refactor cannot quietly
drop one again, and pin the safe forms so closing the gap does not buy recall
with false positives.
"""

import pytest

from backend.app.services.security_analyzer import detect_security_issues


def _deser_findings(code):
    issues = detect_security_issues(code, is_test_file=False, file_path="app.py")
    return [i for i in issues
            if "deserial" in str(i.get("issue_type", "")).lower()
            or "deserial" in str(i.get("description", "")).lower()]


# ----------------------------------------------------------
# The three sinks that must be caught
# ----------------------------------------------------------

@pytest.mark.parametrize("code, label", [
    ("import pickle\ndef f(b):\n    return pickle.loads(b)\n", "pickle.loads"),
    ("import pickle\ndef f(fp):\n    return pickle.load(fp)\n", "pickle.load"),
    ("import yaml\ndef f(t):\n    return yaml.load(t)\n", "yaml.load"),
])
def test_unsafe_deserialization_sinks_are_detected(code, label):
    """Each of the three planted sinks must produce a finding.

    Would fail if: the detector goes back to matching only the plural `loads`,
    which is what put recall at 0.33.
    """
    found = _deser_findings(code)
    assert found, f"{label} not detected as unsafe deserialization"


# ----------------------------------------------------------
# Safe forms that must stay quiet (recall must not cost precision)
# ----------------------------------------------------------

@pytest.mark.parametrize("code, label", [
    ("import yaml\ndef f(t):\n    return yaml.safe_load(t)\n", "yaml.safe_load"),
    ("import json\ndef f(t):\n    return json.loads(t)\n", "json.loads"),
    ("import json\ndef f(fp):\n    return json.load(fp)\n", "json.load"),
    ("import yaml\ndef f(t):\n    return yaml.load(t, Loader=yaml.SafeLoader)\n",
     "yaml.load with SafeLoader"),
    ("import yaml\ndef f(t):\n    return yaml.load(t, Loader=yaml.CSafeLoader)\n",
     "yaml.load with CSafeLoader"),
])
def test_safe_deserialization_forms_are_not_flagged(code, label):
    """Widening the sink list must not start crying wolf.

    `yaml.load(x, Loader=SafeLoader)` is the documented safe spelling and is
    common in real code; flagging it would trade the recall win for a precision
    loss on exactly the repos the benchmark measures.

    Would fail if: the widened matcher keys on the attribute name alone and
    ignores the Loader argument.
    """
    found = _deser_findings(code)
    assert not found, f"{label} wrongly flagged: {found}"


def test_yaml_load_with_unsafe_loader_is_still_flagged():
    """An explicit unsafe Loader is not a free pass."""
    code = "import yaml\ndef f(t):\n    return yaml.load(t, Loader=yaml.Loader)\n"
    assert _deser_findings(code), "yaml.load with the unsafe Loader was missed"


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
