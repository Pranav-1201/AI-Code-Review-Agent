# ==========================================================
# File: llm_service.py
# Purpose: Core AI code analysis service combining
#          RAG retrieval + transformer inference +
#          deterministic heuristics.
# ==========================================================

from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch
from typing import Dict, List

from app.config import HF_TOKEN
from app.services.retriever_service import CodeRetriever
from app.services.security_analyzer import detect_security_issues
from app.services.quality_scorer import compute_quality_score

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

    issues = []
    complexity = "O(n)"

    if loop_count >= 2:
        complexity = "O(n^2)"
        issues.append("Nested loops detected")

    if condition_count > 0 and loop_count > 0:
        issues.append("Conditional logic inside loops may affect performance")

    if not issues:
        issues.append("No obvious structural issues detected")

    return issues, complexity


# ----------------------------------------------------------
# Main Code Analysis Function
# ----------------------------------------------------------
from typing import Dict, List

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

    issues = ["No obvious structural issues detected"]

    quality_score = compute_quality_score(
        probs[1],
        complexity,
        security_issues
    )

    # ------------------------------------------------------
    # STEP 6: Generate explanation
    # ------------------------------------------------------

    explanation = (
        "The system combines transformer-based semantic analysis "
        "with static heuristics to detect inefficiencies."
    )

    suggestions = []

    if complexity == "O(n^2)":
        suggestions.append(
            "Consider reducing nested loops using sets or hash maps."
        )
    else:
        suggestions.append(
            "Code structure appears efficient for typical input sizes."
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