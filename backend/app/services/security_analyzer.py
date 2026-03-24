# ==========================================================
# File: security_analyzer.py
# Purpose: Detect common security vulnerabilities in code
# ==========================================================

from typing import List
import re


def detect_security_issues(code: str) -> List[str]:
    """
    Detect simple security vulnerabilities using pattern checks.
    """

    issues = []

    # ------------------------------------------------------
    # Dangerous execution functions
    # ------------------------------------------------------

    if re.search(r"\beval\s*\(", code):
        issues.append(
            "Use of eval() detected which may allow arbitrary code execution."
        )

    if re.search(r"\bexec\s*\(", code):
        issues.append(
            "Use of exec() detected which may allow execution of unsafe code."
        )

    # ------------------------------------------------------
    # Command execution risks
    # ------------------------------------------------------

    if re.search(r"os\.system\s*\(", code):
        issues.append(
            "Use of os.system() detected which may allow command injection."
        )

    if re.search(r"subprocess\.(Popen|call|run)\s*\(", code):
        issues.append(
            "Use of subprocess without sanitization may allow command injection."
        )

    # ------------------------------------------------------
    # Hardcoded credential detection
    # ------------------------------------------------------

    credential_patterns = [
        r"password\s*=",
        r"passwd\s*=",
        r"secret\s*=",
        r"api_key\s*=",
        r"token\s*="
    ]

    for pattern in credential_patterns:
        if re.search(pattern, code, re.IGNORECASE):
            issues.append("Possible hardcoded credential detected.")
            break

    # ------------------------------------------------------
    # Simple SQL injection pattern
    # ------------------------------------------------------

    if re.search(r"SELECT .* \+ .*", code, re.IGNORECASE):
        issues.append(
            "Possible SQL injection via string concatenation."
        )

    return issues