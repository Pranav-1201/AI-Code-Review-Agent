from app.services.llm_service import analyze_code
from app.analysis.patch_generator import PatchGenerator


class LLMRefactorEngine:

    def __init__(self):
        self.patch_generator = PatchGenerator()

    def generate_refactor(self, code, complexity, smells):
        """
        Generate AI-assisted refactoring suggestions using the existing
        explainable analysis pipeline.
        """

        # Run existing AI analysis
        analysis_result = analyze_code(code)

        explanation = analysis_result["analysis"]["explanation"]
        suggestions = analysis_result["analysis"]["suggestions"]

        # Default improved code (same as original)
        improved_code = code

        # Simple automatic refactoring example for nested loops
        if complexity.get("max_loop_depth", 0) >= 2:
            improved_code = """
                def process(arr):
                    seen = set(arr)
                    for value in seen:
                        print(value)
                """

        # Generate diff patch
        patch = self.patch_generator.generate_patch(code, improved_code)

        return {
            "explanation": explanation,
            "suggestions": suggestions,
            "improved_code": improved_code,
            "patch": patch
        }