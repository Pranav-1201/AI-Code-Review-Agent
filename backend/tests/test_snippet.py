"""Unit tests for the snippet extractor.

The point of this module is that a finding can show its evidence. The tests
that matter most are the ones asserting it returns "" rather than a sentence
when there is no evidence — the field it replaces used to emit
"Line 481 indicates: Command Injection" whether or not any source was known.
"""

from backend.app.services.snippet import MAX_LINE_CHARS, extract_snippet

SOURCE = [
    "import subprocess",
    "",
    "",
    "class Runner:",
    "    def run(self, cmd):",
    "        if cmd:",
    "            subprocess.run(cmd, shell=True)",
    "        return None",
]


def test_returns_the_flagged_line_with_two_lines_of_context():
    out = extract_snippet(SOURCE, 7)

    # Line 7 is the subprocess call; 5..9 clipped to 5..8 by the file end.
    assert out.splitlines() == [
        "5: def run(self, cmd):",
        "6:     if cmd:",
        "7:         subprocess.run(cmd, shell=True)",
        "8:     return None",
    ]


def test_strips_the_common_indent_but_keeps_relative_indent():
    out = extract_snippet(SOURCE, 7)

    # The window's shallowest non-blank line is `def run` at 4 spaces, so 4
    # come off every line and `subprocess.run` keeps the 4 that remain.
    assert "5: def run(self, cmd):" in out
    assert "7:         subprocess.run(cmd, shell=True)" in out


def test_clamps_at_the_first_line():
    out = extract_snippet(SOURCE, 1)

    assert out.splitlines() == [
        "1: import subprocess",
        "2: ",
        "3: ",
    ]


def test_clamps_at_the_last_line():
    out = extract_snippet(SOURCE, 8)

    assert out.splitlines() == [
        "6: if cmd:",
        "7:     subprocess.run(cmd, shell=True)",
        "8: return None",
    ]


def test_truncates_a_very_long_line():
    out = extract_snippet(["x = " + "a" * 500], 1)

    body = out.split(": ", 1)[1]
    assert len(body) == MAX_LINE_CHARS + 1  # the cap plus the ellipsis
    assert body.endswith("…")


def test_returns_empty_string_when_there_is_no_source():
    assert extract_snippet([], 5) == ""


def test_returns_empty_string_when_the_line_is_out_of_range():
    assert extract_snippet(SOURCE, 99) == ""


def test_returns_empty_string_for_a_zero_or_negative_line():
    # `line` defaults to 0 all over the analyzer for "position unknown".
    assert extract_snippet(SOURCE, 0) == ""
    assert extract_snippet(SOURCE, -3) == ""


def test_context_width_is_adjustable():
    out = extract_snippet(SOURCE, 7, context=1)

    assert out.splitlines() == [
        "6: if cmd:",
        "7:     subprocess.run(cmd, shell=True)",
        "8: return None",
    ]
