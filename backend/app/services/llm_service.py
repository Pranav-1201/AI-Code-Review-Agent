# ==========================================================
# File: llm_service.py
# Purpose: Core AI code analysis service combining
#          RAG retrieval + transformer inference +
#          deterministic heuristics.
# ==========================================================

from transformers import AutoTokenizer, AutoModelForSequenceClassification
import ast
import torch
from typing import Dict, List

from backend.app.config import HF_TOKEN
from backend.app.services.retriever_service import CodeRetriever
from backend.app.services.security_analyzer import detect_security_issues
from backend.app.services.quality_scorer import compute_quality_score

MODEL_NAME = "microsoft/codebert-base"

# ----------------------------------------------------------
# Global cached objects (loaded once)
# ----------------------------------------------------------

_tokenizer = None
_model = None
_retriever = None


# ----------------------------------------------------------
# Model Loader (safe lazy loading)
# ----------------------------------------------------------

def load_model():
    global _tokenizer, _model

    if _tokenizer is None:
        _tokenizer = AutoTokenizer.from_pretrained(
            MODEL_NAME,
            token=HF_TOKEN
        )

    if _model is None:
        _model = AutoModelForSequenceClassification.from_pretrained(
            MODEL_NAME,
            num_labels=2,
            token=HF_TOKEN
        )


# ----------------------------------------------------------
# Retriever Loader
# ----------------------------------------------------------

def get_retriever():
    global _retriever

    if _retriever is None:
        _retriever = CodeRetriever()

    return _retriever


# ----------------------------------------------------------
# Heuristic Analysis
# ----------------------------------------------------------

def _heuristic_analysis(code: str, complexity: str = "O(1)", filename: str = ""):
    """
    Perform heuristic code analysis for structural issues.
    Complexity is provided by the caller (from ComplexityAnalyzer),
    NOT re-calculated here — single source of truth.
    """

    # Use TOTAL line count (matching wc -l), not stripped
    line_count = len(code.splitlines())
    lines = [l.strip() for l in code.split("\n") if l.strip()]

    issues = []

    # --------------------------------------------------
    # Generate performance issue from complexity param
    # --------------------------------------------------

    if complexity in ("O(n³)", "O(n^3)", "O(n^k)"):
        issues.append({
            "type": "performance",
            "severity": "high",
            "message": "Deeply nested loops detected — high time complexity."
        })
    elif complexity in ("O(n²)", "O(n^2)"):
        issues.append({
            "type": "performance",
            "severity": "medium",
            "message": "Nested loop detected (depth 2) — possible performance bottleneck."
        })

    # --------------------------------------------------
    # Cyclomatic branching check (only when nesting exists)
    # --------------------------------------------------

    condition_count = sum(1 for l in lines if l.lstrip().startswith(("if ", "elif ")))
    if condition_count > 10 and complexity not in ("O(1)", "O(n)"):
        issues.append({
            "type": "maintainability",
            "severity": "medium",
            "message": f"High cyclomatic complexity: high branching ({condition_count} conditions) combined with deep nesting."
        })

    # Detect long files
    if line_count > 300:
        issues.append({
            "type": "maintainability",
            "severity": "medium",
            "message": f"File is {line_count} lines long \u2014 consider splitting into smaller modules"
        })
    elif line_count > 150:
        issues.append({
            "type": "style",
            "severity": "low",
            "message": f"File is {line_count} lines \u2014 approaching recommended module size limit"
        })

    # --------------------------------------------------
    # Detect missing if __name__ guard
    # Skip for __main__.py — it IS the entry point by
    # definition, the guard is meaningless there.
    # --------------------------------------------------

    basename = filename.replace("\\", "/").split("/")[-1].lower() if filename else ""
    is_main_module = basename == "__main__.py"

    if not is_main_module:
        has_main_guard = any("__name__" in l and "__main__" in l for l in lines)

        script_execution_patterns = (
            ".run(", "main(", "sys.exit(", "app.run(",
            "cli(", "click.command", "argparse"
        )
        has_script_execution = any(
            any(pat in l for pat in script_execution_patterns)
            for l in lines
            if l and not l.startswith(("def ", "class ", "#", "@", " ", "\t"))
        )

        if has_script_execution and not has_main_guard:
            issues.append({
                "type": "style",
                "severity": "low",
                "message": "Top-level function calls detected without if __name__ == '__main__' guard"
            })

    return issues


# ----------------------------------------------------------
# Generate File-Specific Explanation
# ----------------------------------------------------------

def _generate_explanation(
    code: str,
    issues: List[Dict],
    security_issues: List[Dict],
    complexity: str,
    quality_score: int,
    functions: List[str],
    imports: List[str],
    language: str,
    doc_coverage: float = 0.0
) -> str:
    """
    Generate a meaningful, file-specific explanation
    based on actual analysis signals.
    """

    total_lines = len(code.splitlines())
    parts = []

    # Overview
    if functions:
        fn_list = ", ".join(functions[:5])
        suffix = f" and {len(functions) - 5} more" if len(functions) > 5 else ""
        parts.append(f"This {language} file defines {len(functions)} function(s): {fn_list}{suffix}.")
    else:
        parts.append(f"This {language} file contains {total_lines} lines with no explicit function definitions.")

    # Quality assessment
    if quality_score >= 90:
        parts.append("Code quality is excellent with minimal issues detected.")
    elif quality_score >= 75:
        parts.append("Code quality is good with minor areas for improvement.")
    elif quality_score >= 50:
        parts.append("Code quality is moderate — several improvements recommended.")
    else:
        parts.append("Code quality needs significant improvement.")

    # Complexity note
    if complexity not in ("O(1)", "O(n)"):
        parts.append(f"Estimated time complexity is {complexity}, which may impact performance on large inputs.")

    # Documentation coverage note
    if functions and doc_coverage < 100.0:
        documented = int(len(functions) * doc_coverage / 100)
        missing = len(functions) - documented
        parts.append(f"Documentation coverage: {doc_coverage}% ({missing} of {len(functions)} functions lack docstrings).")

    # Security note
    if security_issues:
        sev_counts = {}
        for s in security_issues:
            sev = s.get("severity", "Medium") if isinstance(s, dict) else "High"
            sev_counts[sev] = sev_counts.get(sev, 0) + 1
        sev_str = ", ".join(f"{v} {k}" for k, v in sorted(sev_counts.items()))
        parts.append(f"Security analysis found {len(security_issues)} issue(s) ({sev_str}).")

    # Structural issues note
    real_issues = [i for i in issues if isinstance(i, dict)]
    if real_issues:
        categories = set(i.get("type", "general") for i in real_issues)
        parts.append(f"Static analysis detected {len(real_issues)} structural/style issue(s) in categories: {', '.join(sorted(categories))}.")

    return " ".join(parts)


# ----------------------------------------------------------
# Generate File-Specific Suggestions
# ----------------------------------------------------------

def _generate_suggestions(
    complexity: str,
    security_issues: List[Dict],
    issues: List[Dict],
    functions: List[str],
    imports: List[str],
    code: str
) -> List[str]:
    """
    Generate actionable, file-specific suggestions
    based on actual analysis signals.
    """

    suggestions = []

    # Complexity suggestions
    if complexity in ("O(n^2)", "O(n^3)", "O(n^k)"):
        suggestions.append(
            "Consider reducing nested loops using sets, hash maps, or vectorized operations for better performance."
        )

    # Security suggestions
    if security_issues:
        sec_types = set()
        for s in security_issues:
            if isinstance(s, dict):
                sec_types.add(s.get("type", "security"))
        if "Hardcoded Credential" in sec_types:
            suggestions.append("Move hardcoded credentials to environment variables or a secrets manager.")
        if "SQL Injection" in sec_types:
            suggestions.append("Use parameterized queries or an ORM instead of string concatenation for SQL.")
        if "Command Injection" in sec_types:
            suggestions.append("Use subprocess with list arguments instead of shell commands.")

    # Long file suggestion
    lines = len([l for l in code.split("\n") if l.strip()])
    if lines > 200:
        suggestions.append(
            f"This file has {lines} lines. Consider splitting it into smaller, focused modules."
        )

    # Many functions suggestion
    if len(functions) > 15:
        suggestions.append(
            f"This file defines {len(functions)} functions. Consider grouping related functions into separate modules or classes."
        )

    # Many imports suggestion
    if len(imports) > 10:
        suggestions.append(
            f"This file has {len(imports)} imports — review for unused imports and consider lazy loading."
        )

    # Fallback if nothing specific
    if not suggestions:
        if complexity == "O(1)":
            suggestions.append("Code structure appears efficient for typical input sizes.")
        else:
            suggestions.append("Code complexity is manageable. Consider adding docstrings for better documentation.")

    return suggestions


# ----------------------------------------------------------
# Main Code Analysis Function
# ----------------------------------------------------------

def analyze_code(
    code: str,
    functions: List[str] = None,
    imports: List[str] = None,
    complexity_metrics: List[Dict] = None,
    language: str = "unknown",
    security_issues: List[Dict] = None,
    is_test_file: bool = False
) -> Dict:
    """
    Main code analysis function combining AI inference,
    heuristic analysis, and security scanning.

    Parameters
    ----------
    security_issues : List[Dict], optional
        Pre-computed security issues from the caller.
        If provided, detect_security_issues() is NOT called
        (eliminates duplicate analysis).
    is_test_file : bool
        If True and security_issues is None, passes context
        to detect_security_issues for filtering.
    """

    load_model()

    functions = functions or []
    imports = imports or []

    # ------------------------------------------------------
    # STEP 1: Retrieve repository context (RAG)
    # ------------------------------------------------------

    try:
        context_chunks = get_retriever().retrieve(code)
    except Exception:
        context_chunks = []

    context_text = "\n".join(context_chunks[:3])  # limit context size

    # ------------------------------------------------------
    # STEP 2: Build prompt
    # ------------------------------------------------------

    prompt = f"""
Repository Context:
{context_text}

Code:
{code}
"""

    # ------------------------------------------------------
    # STEP 3: Tokenize
    # ------------------------------------------------------

    inputs = _tokenizer(
        prompt,
        return_tensors="pt",
        truncation=True,
        max_length=512
    )

    # ------------------------------------------------------
    # STEP 4: Model inference
    # ------------------------------------------------------

    with torch.no_grad():
        outputs = _model(**inputs)

    probs = torch.softmax(outputs.logits, dim=1).tolist()[0]

    # ------------------------------------------------------
    # STEP 5: Security analysis
    # Use pre-computed issues from caller when available
    # to avoid duplicate analysis (single source of truth)
    # ------------------------------------------------------

    if security_issues is None:
        security_issues = detect_security_issues(code, is_test_file=is_test_file)

    # ----------------------------------------------
    # Complexity from AST analyzer
    # ----------------------------------------------

    complexity = "O(1)"

    if complexity_metrics:

        nested_depth = max(
            fn.get("max_loop_depth", 0)
            for fn in complexity_metrics
        )

        if nested_depth == 1:
            complexity = "O(n)"

        elif nested_depth == 2:
            complexity = "O(n\u00b2)"

        elif nested_depth >= 3:
            complexity = "O(n^k)"

    # ------------------------------------------------------
    # Heuristic issue detection
    # Single source of truth: complexity comes from the
    # ComplexityAnalyzer (path 1 above). _heuristic_analysis
    # generates issue messages FROM that complexity, not
    # its own competing calculation.
    # ------------------------------------------------------

    # Extract filename for __main__.py guard suppression
    _filename = ""
    if complexity_metrics and len(complexity_metrics) > 0:
        _filename = complexity_metrics[0].get("_filename", "")

    heuristic_issues = _heuristic_analysis(code, complexity=complexity, filename=_filename)

    # Merge heuristic issues (already structured dicts)
    issues = list(heuristic_issues)

    quality_score = compute_quality_score(
        probs[1],
        complexity,
        security_issues,
        is_test_file=is_test_file
    )

    # ------------------------------------------------------
    # STEP 6: Generate file-specific explanation
    # ------------------------------------------------------

    # Extract doc coverage if available from complexity_metrics metadata
    _doc_coverage = 0.0
    if complexity_metrics and len(complexity_metrics) > 0:
        _doc_coverage = complexity_metrics[0].get("_doc_coverage", 0.0)

    explanation = _generate_explanation(
        code=code,
        issues=issues,
        security_issues=security_issues,
        complexity=complexity,
        quality_score=quality_score,
        functions=functions,
        imports=imports,
        language=language,
        doc_coverage=_doc_coverage
    )

    suggestions = _generate_suggestions(
        complexity=complexity,
        security_issues=security_issues,
        issues=issues,
        functions=functions,
        imports=imports,
        code=code
    )

    # ------------------------------------------------------
    # STEP 7: Structured result
    # ------------------------------------------------------

    return {
        "language": language,
        "confidence_scores": {
            "issue_likely": round(probs[1], 3),
            "issue_unlikely": round(probs[0], 3)
        },
        "code_quality_score": quality_score,
        "analysis": {
            "issues": issues,
            "security_risks": security_issues,
            "time_complexity": complexity,
            "explanation": explanation,
            "suggestions": suggestions
        },
        "retrieved_context": context_chunks
    }