"""Phase K / F10 — the UI's language list must match the analyzer's.

The scanner page states which languages ETPROJECT analyses before a user
spends a clone finding out. That copy is a promise, and a promise duplicated
in two files drifts. This test parses the frontend constant and fails if it
stops matching the backend, so the drift is caught in CI rather than by a
user who was told a language the analyzer skips.
"""
import os
import re

import pytest

from backend.app.services.repo_analyzer import (
    CODE_EXTENSIONS,
    LANGUAGE_MAP,
    SUPPORTED_LANGUAGES,
)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LANGUAGES_TS = os.path.join(REPO_ROOT, "frontend", "src", "lib", "languages.ts")


def _frontend_languages():
    with open(LANGUAGES_TS, encoding="utf-8") as fh:
        source = fh.read()
    body = re.search(
        r"export const SUPPORTED_LANGUAGES\s*=\s*\[(.*?)\]\s*as const;",
        source,
        re.DOTALL,
    )
    assert body, f"could not find SUPPORTED_LANGUAGES in {LANGUAGES_TS}"
    return tuple(re.findall(r'"([^"]+)"', body.group(1)))


def test_the_frontend_list_matches_the_backend_exactly():
    assert _frontend_languages() == tuple(SUPPORTED_LANGUAGES)


def test_every_advertised_language_has_an_extension_we_actually_scan():
    """Advertising a language the walker never picks up is a false promise."""
    scanned = {LANGUAGE_MAP.get(ext) for ext in CODE_EXTENSIONS}
    missing = [lang for lang in SUPPORTED_LANGUAGES if lang not in scanned]
    assert not missing, f"advertised but never scanned: {missing}"
