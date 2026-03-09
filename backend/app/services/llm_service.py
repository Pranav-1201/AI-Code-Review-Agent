from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch

from app.config import HF_TOKEN
from app.services.retriever_service import CodeRetriever

from app.services.security_analyzer import detect_security_issues
from app.services.quality_scorer import compute_quality_score

MODEL_NAME = "microsoft/codebert-base"

# Initialize retriever once (avoid reloading each request)
retriever = CodeRetriever()

# Load tokenizer
tokenizer = AutoTokenizer.from_pretrained(
    MODEL_NAME,
    token=HF_TOKEN
)

# Load model
model = AutoModelForSequenceClassification.from_pretrained(
    MODEL_NAME,
    num_labels=2,
    token=HF_TOKEN
)


def _heuristic_analysis(code: str):
    """
    Deterministic heuristics to support explainability.
    """

    lines = [l.strip() for l in code.strip().split("\n") if l.strip()]

    loop_count = sum(1 for l in lines if l.startswith("for "))
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


def analyze_code(code: str, language: str = "unknown") -> dict:
    """
    Explainable code analysis using:
    1. RAG repository context retrieval
    2. LLM semantic signals (CodeBERT)
    3. Deterministic heuristics
    """

    # -----------------------------
    # STEP 1: Retrieve repository context (RAG)
    # -----------------------------

    try:
        context_chunks = retriever.retrieve(code)
    except Exception:
        context_chunks = []

    context_text = "\n".join(context_chunks)

    # -----------------------------
    # STEP 2: Build contextual prompt
    # -----------------------------

    prompt = f"""
You are an AI code reviewer.

Repository Context:
{context_text}

Code To Review:
{code}

Analyze the code and determine if it contains inefficiencies,
logical problems, or poor structural patterns.
"""

    # -----------------------------
    # STEP 3: Tokenize input
    # -----------------------------

    inputs = tokenizer(
        prompt,
        return_tensors="pt",
        truncation=True,
        max_length=512
    )

    # -----------------------------
    # STEP 4: Run model inference
    # -----------------------------

    with torch.no_grad():
        outputs = model(**inputs)

    probs = torch.softmax(outputs.logits, dim=1).tolist()[0]
    issue_probability = probs[1]

    # -----------------------------
    # STEP 5: Run heuristic analysis
    # -----------------------------

    issues, complexity = _heuristic_analysis(code)
    security_issues = detect_security_issues(code)
    quality_score = compute_quality_score(
        issue_probability,
        complexity,
        security_issues
    )

    # -----------------------------
    # STEP 6: Generate explanation
    # -----------------------------

    explanation = (
        "The analysis combines semantic representations from a "
        "pretrained transformer model with deterministic code pattern checks. "
        f"The estimated time complexity is {complexity}."
    )

    suggestions = []

    if complexity == "O(n^2)":
        suggestions.append(
            "Try reducing nested loops using data structures such as hash maps or sets."
        )
    else:
        suggestions.append(
            "The code structure appears efficient for typical input sizes."
        )

    # -----------------------------
    # STEP 7: Return structured output
    # -----------------------------

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