# ==========================================================
# File: llm_service.py
# Purpose: Core AI code analysis service combining
#          RAG retrieval + transformer inference +
#          deterministic heuristics.
# ==========================================================

from transformers import AutoTokenizer, AutoModelForSequenceClassification
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

def _heuristic_analysis(code: str):

    lines = [l.strip() for l in code.split("\n") if l.strip()]

    loop_count = sum(1 for l in lines if l.startswith(("for ", "while ")))
    condition_count = sum(1 for l in lines if "if " in l)
    line_count = len(lines)

    issues = []

    # Detect potential performance issues
    if loop_count >= 2:
        issues.append({
            "type": "performance",
            "severity": "medium",
            "message": f"Multiple loops detected ({loop_count} loops) — possible nested loop performance issue"
        })

    if condition_count > 0 and loop_count > 0:
        issues.append({
            "type": "performance",
            "severity": "low",
            "message": "Conditional logic inside loops may affect performance"
        })

    # Detect long files
    if line_count > 200:
        issues.append({
            "type": "maintainability",
            "severity": "medium",
            "message": f"File is {line_count} lines long — consider splitting into smaller modules"
        })
    elif line_count > 100:
        issues.append({
            "type": "style",
            "severity": "low",
            "message": f"File is {line_count} lines — approaching recommended module size limit"
        })

    # Detect missing if __name__ guard in scripts with top-level code
    has_main_guard = any("__name__" in l and "__main__" in l for l in lines)
    has_top_level_calls = any(
        l and not l.startswith(("def ", "class ", "import ", "from ", "#", "@", "    "))
        and "=" not in l
        and l.endswith(")")
        for l in lines
    )
    if has_top_level_calls and not has_main_guard:
        issues.append({
            "type": "style",
            "severity": "low",
            "message": "Top-level function calls detected without if __name__ == '__main__' guard"
        })

    # Complexity heuristic
    complexity = "O(1)"
    if loop_count >= 3:
        complexity = "O(n^3)"
    elif loop_count >= 2:
        complexity = "O(n^2)"
    elif loop_count >= 1:
        complexity = "O(n)"

    return issues, complexity


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
    language: str
) -> str:
    """
    Generate a meaningful, file-specific explanation
    based on actual analysis signals.
    """

    lines = len([l for l in code.split("\n") if l.strip()])
    parts = []

    # Overview
    if functions:
        fn_list = ", ".join(functions[:5])
        suffix = f" and {len(functions) - 5} more" if len(functions) > 5 else ""
        parts.append(f"This {language} file defines {len(functions)} function(s): {fn_list}{suffix}.")
    else:
        parts.append(f"This {language} file contains {lines} lines of code with no explicit function definitions.")

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

    # Security note
    if security_issues:
        sev_counts = {}
        for s in security_issues:
            sev = s.get("severity", "Medium") if isinstance(s, dict) else "High"
            sev_counts[sev] = sev_counts.get(sev, 0) + 1
        sev_str = ", ".join(f"{v} {k}" for k, v in sorted(sev_counts.items()))
        parts.append(f"Security analysis found {len(security_issues)} issue(s) ({sev_str}).")

    # Issues note
    real_issues = [i for i in issues if isinstance(i, dict)]
    if real_issues:
        categories = set(i.get("type", "general") for i in real_issues)
        parts.append(f"Static analysis detected {len(real_issues)} issue(s) in categories: {', '.join(categories)}.")

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
    language: str = "unknown"
) -> Dict:

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
    # STEP 5: Static security + default complexity
    # ------------------------------------------------------

    security_issues = detect_security_issues(code)

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
            complexity = "O(n^2)"

        elif nested_depth >= 3:
            complexity = "O(n^k)"

    # ------------------------------------------------------
    # Heuristic issue detection
    # ------------------------------------------------------

    heuristic_issues, heuristic_complexity = _heuristic_analysis(code)

    # Merge heuristic issues (already structured dicts)
    issues = list(heuristic_issues)

    quality_score = compute_quality_score(
        probs[1],
        complexity,
        security_issues
    )

    # ------------------------------------------------------
    # STEP 6: Generate file-specific explanation
    # ------------------------------------------------------

    explanation = _generate_explanation(
        code=code,
        issues=issues,
        security_issues=security_issues,
        complexity=complexity,
        quality_score=quality_score,
        functions=functions,
        imports=imports,
        language=language
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