from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch
from backend.app.config import HF_TOKEN

MODEL_NAME = "microsoft/codebert-base"

# Load tokenizer and model
tokenizer = AutoTokenizer.from_pretrained(
    MODEL_NAME,
    token=HF_TOKEN
)

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
    Explainable code analysis using LLM signals + heuristics.
    """

    prompt = f"""
    Analyze the following {language} code and estimate
    whether it contains inefficiencies or logical issues.

    Code:
    {code}
    """

    inputs = tokenizer(
        prompt,
        return_tensors="pt",
        truncation=True,
        max_length=512
    )

    with torch.no_grad():
        outputs = model(**inputs)

    probs = torch.softmax(outputs.logits, dim=1).tolist()[0]

    issues, complexity = _heuristic_analysis(code)

    explanation = (
        "The analysis combines learned code representations from a "
        "pretrained language model with deterministic pattern checks. "
        f"The estimated time complexity is {complexity}."
    )

    suggestions = []
    if complexity == "O(n^2)":
        suggestions.append(
            "Try reducing nested loops using data structures like hash maps or sets."
        )
    else:
        suggestions.append("The code structure appears efficient for typical inputs.")

    return {
        "language": language,
        "confidence_scores": {
            "issue_likely": round(probs[1], 3),
            "issue_unlikely": round(probs[0], 3)
        },
        "analysis": {
            "issues": issues,
            "time_complexity": complexity,
            "explanation": explanation,
            "suggestions": suggestions
        }
    }
