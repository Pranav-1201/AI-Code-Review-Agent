import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.analysis.refactoring_engine import RefactoringEngine

complexity = {
    "cyclomatic_complexity": 12,
    "max_loop_depth": 3,
    "recursive": False
}

smells = {
    "code_smells": ["Deep Nesting", "Magic Numbers"]
}

engine = RefactoringEngine()

suggestions = engine.generate_suggestions(complexity, smells)

for s in suggestions:
    print("-", s)