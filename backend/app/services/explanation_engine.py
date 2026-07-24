# ==========================================================
# File: explanation_engine.py
# Location: backend/app/services
#
# Purpose
# ----------------------------------------------------------
# Phase 5: the ONE place a real LLM (Anthropic) is called at
# runtime. It turns the DETERMINISTIC findings from Phases 0-4
# (taint paths, trust boundaries, cohesion score, complexity,
# framework context) into a natural-language explanation.
#
# Honest boundary — this is the line between deterministic and
# generated:
#   * Every FINDING (issue, severity, taint path, trust boundary,
#     score) is produced deterministically by the analysis layer.
#   * This module only paraphrases/teaches those findings. It is
#     instructed to explain ONLY the supplied evidence and never
#     to invent issues.
#
# Gating (mirrors the ENABLE_CODEBERT pattern):
#   * Off unless ENABLE_ANTHROPIC=true AND ANTHROPIC_API_KEY is set.
#   * On failure/timeout/disabled it returns the caller's
#     deterministic explanation verbatim (source="deterministic").
# No SDK dependency — plain urllib. Never logs or hardcodes the key.
# ==========================================================

from __future__ import annotations

import json
import os
import urllib.request
from typing import Any, Dict, List, Optional

ENABLE_ANTHROPIC = os.getenv("ENABLE_ANTHROPIC", "false").lower() == "true"
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
_ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
_ANTHROPIC_VERSION = "2023-06-01"

VALID_DEPTHS = ("junior", "senior")


def anthropic_available() -> bool:
    """True only when explicitly enabled AND a key is present."""
    return ENABLE_ANTHROPIC and bool(os.getenv("ANTHROPIC_API_KEY"))


# ----------------------------------------------------------
# Prompt construction — strictly grounded in the evidence
# ----------------------------------------------------------

def _evidence_block(evidence: Dict[str, Any]) -> str:
    """Render the deterministic findings as a compact, factual brief."""
    lines: List[str] = []
    fn = evidence.get("file_name") or "(unknown file)"
    lines.append(f"File: {fn}  |  Language: {evidence.get('language', 'python')}")
    if evidence.get("framework"):
        lines.append(f"Framework context: {evidence['framework']}")

    cx = evidence.get("complexity") or {}
    lines.append(
        f"Complexity: cyclomatic={cx.get('cyclomatic_complexity', 1)}, "
        f"max_loop_depth={cx.get('max_loop_depth', 0)}, "
        f"quality_score={evidence.get('quality_score', 'n/a')}"
    )
    coh = evidence.get("cohesion") or {}
    if coh.get("should_flag_size"):
        lines.append(
            f"Cohesion: LOW ({coh.get('module_cohesion', 0):.2f}) at "
            f"{coh.get('line_count', '?')} lines — size flagged."
        )
    elif "module_cohesion" in coh:
        lines.append(f"Cohesion: {coh.get('module_cohesion', 0):.2f}")

    sec = evidence.get("security_findings") or []
    if sec:
        lines.append("Security findings (deterministic):")
        for s in sec[:12]:
            tb = s.get("trust_boundary", "n/a")
            lines.append(
                f"  - [{s.get('severity', '?')}] {s.get('type', 'issue')}: "
                f"{s.get('description', '')[:180]} (trust_boundary={tb})"
            )
    issues = evidence.get("issues") or []
    if issues:
        lines.append("Code-quality findings (deterministic):")
        for i in issues[:12]:
            msg = i.get("message", "") if isinstance(i, dict) else str(i)
            lines.append(f"  - {msg[:180]}")
    if not sec and not issues:
        lines.append("No security or structural findings were detected.")
    return "\n".join(lines)


def _build_messages(evidence: Dict[str, Any], depth: str) -> Dict[str, Any]:
    depth = depth if depth in VALID_DEPTHS else "senior"
    if depth == "junior":
        audience = ("Audience: a JUNIOR developer. Define jargon, explain WHY each "
                    "finding matters and how to think about it, and be encouraging. "
                    "A few short paragraphs are fine.")
    else:
        audience = ("Audience: a SENIOR engineer. Be terse and high-signal; assume "
                    "expertise; skip basics; lead with the most important risk. Keep "
                    "it to a few sentences.")

    system = (
        "You are the explanation layer of a static code-analysis tool. A separate "
        "deterministic engine has already produced ALL findings. Your job is to "
        "explain ONLY the findings in the evidence below in plain language.\n"
        "HARD RULES: Do not invent issues, severities, or vulnerabilities that are "
        "not in the evidence. Do not contradict the given trust boundaries or "
        "severities. If a taint trust_boundary is 'untrusted_input', it is remotely "
        "exploitable; if 'operator_input'/'internal', it is not remotely reachable. "
        "If there are no findings, say the file looks clean. Never claim you ran the "
        "analysis yourself.\n" + audience
    )
    user = (
        "Explain this file's review to the developer, grounded strictly in the "
        "deterministic evidence:\n\n" + _evidence_block(evidence)
    )
    return {"system": system, "user": user}


# ----------------------------------------------------------
# Anthropic call (urllib; gated; silent-fail)
# ----------------------------------------------------------

def _call_anthropic(system: str, user: str, max_tokens: int = 1024) -> Optional[str]:
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        return None
    payload = json.dumps({
        "model": ANTHROPIC_MODEL,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }).encode("utf-8")
    req = urllib.request.Request(
        _ANTHROPIC_URL, data=payload,
        headers={
            "x-api-key": key,
            "anthropic-version": _ANTHROPIC_VERSION,
            "content-type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        data = json.loads(response.read().decode("utf-8"))
    parts = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]
    text = "\n".join(p for p in parts if p).strip()
    return text or None


# ----------------------------------------------------------
# Public API
# ----------------------------------------------------------

def generate_explanation(evidence: Dict[str, Any], deterministic_fallback: str,
                         depth: str = "senior") -> Dict[str, Any]:
    """
    Return {"text", "source", "model"}. source is "llm" when a real Anthropic
    response was produced, else "deterministic" (the caller's fallback verbatim).
    Never raises — any failure degrades to the deterministic explanation.
    """
    if not anthropic_available():
        return {"text": deterministic_fallback, "source": "deterministic", "model": None}
    try:
        msgs = _build_messages(evidence, depth)
        text = _call_anthropic(msgs["system"], msgs["user"])
        if text:
            return {"text": text, "source": "llm", "model": ANTHROPIC_MODEL}
    except Exception:
        pass
    return {"text": deterministic_fallback, "source": "deterministic", "model": None}
