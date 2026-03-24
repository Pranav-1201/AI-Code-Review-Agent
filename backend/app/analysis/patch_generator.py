import difflib


class PatchGenerator:

    def generate_patch(self, original_code: str, improved_code: str):
        """
        Generates a unified diff patch between original and improved code.
        """

        original_lines = original_code.splitlines()
        improved_lines = improved_code.splitlines()

        diff = difflib.unified_diff(
            original_lines,
            improved_lines,
            fromfile="original",
            tofile="improved",
            lineterm=""
        )

        return "\n".join(diff)