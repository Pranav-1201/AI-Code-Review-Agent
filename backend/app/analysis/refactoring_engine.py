class RefactoringEngine:

    def generate_suggestions(self, complexity, smells):

        suggestions = []

        # Complexity based suggestions
        if complexity["cyclomatic_complexity"] > 10:
            suggestions.append(
                "Function has high cyclomatic complexity. Consider splitting it into smaller functions."
            )

        if complexity["max_loop_depth"] >= 3:
            suggestions.append(
                "Deep loop nesting detected. Consider using a dictionary or hash map instead of nested loops."
            )

        if complexity["recursive"]:
            suggestions.append(
                "Recursive function detected. Consider memoization or dynamic programming if performance is critical."
            )

        # Code smell suggestions
        for smell in smells["code_smells"]:

            if smell == "Long Function":
                suggestions.append(
                    "Function is too long. Break it into smaller reusable functions."
                )

            if smell == "Deep Nesting":
                suggestions.append(
                    "Deep nesting detected. Refactor using guard clauses or helper functions."
                )

            if smell == "Magic Numbers":
                suggestions.append(
                    "Magic numbers detected. Replace them with named constants."
                )

            if smell == "God Function":
                suggestions.append(
                    "This function does too many things. Consider applying the Single Responsibility Principle."
                )

        return suggestions