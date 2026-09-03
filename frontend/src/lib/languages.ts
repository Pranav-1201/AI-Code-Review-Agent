/**
 * The languages this tool actually analyses.
 *
 * F10 — stated up front in the scanner so a user learns the boundary before
 * waiting for a clone, rather than from the B6 rejection afterwards.
 *
 * This list MUST match `SUPPORTED_LANGUAGES` in
 * `backend/app/services/repo_analyzer.py`. It is duplicated rather than
 * fetched because it is static copy on a page that renders before any request
 * is made — but the duplication is guarded:
 * `backend/tests/test_supported_languages_contract.py` parses this file and
 * fails if the two lists diverge, so drift is caught in CI and not by a user
 * who was promised a language the analyzer skips.
 */
export const SUPPORTED_LANGUAGES = [
  "Python",
  "JavaScript",
  "TypeScript",
  "Java",
  "C",
  "C++",
] as const;
