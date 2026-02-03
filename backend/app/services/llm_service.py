from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch
from backend.app.config import HF_TOKEN

MODEL_NAME = "microsoft/codebert-base"

tokenizer = AutoTokenizer.from_pretrained(
    MODEL_NAME,
    token=HF_TOKEN
)

# Using a generic head for scoring/analysis signals
model = AutoModelForSequenceClassification.from_pretrained(
    MODEL_NAME,
    num_labels=2,
    token=HF_TOKEN
)

def analyze_code(code: str, language: str = "unknown") -> dict:
    """
    Analyze source code and return structured, explainable signals.
    """
    prompt = f"""
    Analyze the following {language} code.
    Identify:
    - Possible logical issues
    - Time/space complexity hints
    - Code smells or bad practices
    Provide a concise explanation.

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

    logits = outputs.logits
    score = torch.softmax(logits, dim=1).tolist()[0]

    # v1 structured output (we'll enrich later)
    result = {
        "language": language,
        "confidence_scores": {
            "issue_likely": round(score[1], 3),
            "issue_unlikely": round(score[0], 3)
        },
        "analysis": {
            "summary": "Initial LLM-based analysis completed.",
            "notes": [
                "This is a preliminary reasoning layer.",
                "Deeper explanations will be added using RAG and agents."
            ]
        }
    }

    return result
