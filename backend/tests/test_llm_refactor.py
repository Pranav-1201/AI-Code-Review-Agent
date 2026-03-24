import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.analysis.llm_refactor_engine import LLMRefactorEngine
from app.services.llm_service import analyze_code

code = """
def process(arr):
    for i in arr:
        for j in arr:
            if i == j:
                print(i)
"""

complexity = {
    "cyclomatic_complexity": 4,
    "max_loop_depth": 2
}

smells = ["Deep Nesting"]

engine = LLMRefactorEngine()

result = engine.generate_refactor(code, complexity, smells)

print("\nExplanation:\n")
print(result["explanation"])

print("\nImproved Code:\n")
print(result["improved_code"])

print("\nPatch:\n")
print(result["patch"])