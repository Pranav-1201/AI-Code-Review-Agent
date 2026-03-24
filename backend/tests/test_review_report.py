import sys
import os

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.append(project_root)
sys.path.append(os.path.join(project_root, "backend"))

from app.services.report_generator import generate_review_report
from database.review_repository import save_review
from rag.vector_store import ReviewVectorStore

# Fake analysis output (simulates llm_service output)
analysis_result = {
    "language": "python",
    "code_quality_score": 82,
    "analysis": {
        "issues": ["Nested loops detected"],
        "security_risks": [],
        "time_complexity": "O(n^2)",
        "suggestions": [
            "Try reducing nested loops using sets or hash maps."
        ]
    }
}

# Fake refactor output (simulates LLMRefactorEngine)
refactor_result = {
    "explanation": "Nested loops cause quadratic time complexity.",
    "improved_code": """
def process(arr):
    seen = set(arr)
    for value in seen:
        print(value)
""",
    "patch": """--- original
+++ improved
@@
- for i in arr:
-     for j in arr:
+ seen = set(arr)
+ for value in seen:
"""
}

complexity_metrics = {
    "cyclomatic_complexity": 4,
    "max_loop_depth": 2
}

smell_metrics = {
    "code_smells": ["Deep Nesting"]
}


report = generate_review_report(
    file_name="example.py",
    analysis_result=analysis_result,
    refactor_result=refactor_result,
    complexity_metrics=complexity_metrics,
    smell_metrics=smell_metrics
)

print(report)