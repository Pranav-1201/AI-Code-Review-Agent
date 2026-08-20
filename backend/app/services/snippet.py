"""Extract the source behind a finding.

A finding that names a line and shows nothing asks the reader to trust it.
This turns a (source, line) pair into a short, self-locating excerpt.

Deliberately stdlib-only and free of any analyzer import: two unrelated call
sites need it — the per-file security analyzer and the inter-procedural taint
pass — and neither should have to import the other to get it.
"""

from __future__ import annotations

# Minified and generated sources have single lines thousands of characters
# long. Uncapped they would bloat every cached scan and blow out the layout of
# the pane that renders them.
MAX_LINE_CHARS = 200


def extract_snippet(source_lines: list[str], line: int, context: int = 2) -> str:
    """Return `line` plus `context` lines either side, numbered and dedented.

    Returns "" when there is nothing to show — no source, or a line outside
    the file. It never returns a sentence: absent evidence is rendered as
    absent by the UI, and a placeholder string defeats that.
    """
    if not source_lines or line <= 0 or line > len(source_lines):
        return ""

    start = max(0, line - 1 - context)          # 0-based, inclusive
    end = min(len(source_lines), line + context)  # 0-based, exclusive
    window = source_lines[start:end]

    # Strip the indent shared by the whole window, so an excerpt from deep
    # inside a class does not render as a column of whitespace. Blank lines
    # carry no indent information and must not drag the common prefix to 0.
    indents = [len(raw) - len(raw.lstrip()) for raw in window if raw.strip()]
    shared = min(indents) if indents else 0

    out = []
    for number, raw in enumerate(window, start=start + 1):
        text = raw[shared:]
        if len(text) > MAX_LINE_CHARS:
            text = text[:MAX_LINE_CHARS] + "…"
        out.append(f"{number}: {text}")

    return "\n".join(out)
