def detect_security_issues(code: str):
    """
    Detect simple security vulnerabilities in code.
    """

    issues = []

    if "eval(" in code:
        issues.append("Use of eval() detected which may allow arbitrary code execution.")

    if "exec(" in code:
        issues.append("Use of exec() detected which may allow execution of unsafe code.")

    if "os.system(" in code:
        issues.append("Use of os.system() detected which may allow command injection.")

    if "subprocess.Popen(" in code:
        issues.append("Use of subprocess without sanitization may allow command injection.")

    if "password =" in code or "passwd =" in code:
        issues.append("Hardcoded credential detected.")

    if "SELECT" in code and "+" in code:
        issues.append("Possible SQL injection via string concatenation.")

    if not issues:
        issues.append("No obvious security vulnerabilities detected.")

    return issues