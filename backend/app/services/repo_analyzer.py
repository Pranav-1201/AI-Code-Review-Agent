import os

from app.analysis.ast_parser import parse_python_file
from app.analysis.dead_code_detector import DeadCodeDetector
from app.analysis.call_graph import build_call_graph
from analysis.complexity_analyzer import ComplexityAnalyzer


SUPPORTED_EXTENSIONS = (".py", ".cpp", ".js", ".java")


class RepoAnalyzer:

    def __init__(self):
        self.dead_code_detector = DeadCodeDetector()

    def analyze_repository(self, repo_path: str):

        files_data = []

        for root, dirs, files in os.walk(repo_path):

            for file in files:

                if file.endswith(SUPPORTED_EXTENSIONS):

                    path = os.path.join(root, file)

                    try:
                        with open(path, "r", encoding="utf-8", errors="ignore") as f:
                            code = f.read()

                        # AST parsing
                        analysis = parse_python_file(code)

                        # Phase 3.8 dead code detection
                        dead_code = self.dead_code_detector.analyze(code)

                        files_data.append({
                            "file_name": file,
                            "file_path": path,
                            "content": code,
                            "functions": analysis["functions"],
                            "imports": analysis["imports"],
                            "dead_code": dead_code
                        })

                    except Exception as e:
                        print(f"Failed to read {path}: {e}")
        # Build repository call graph
        call_graph = build_call_graph(files_data)

        # Detect repository-level unused functions
        unused_functions = self.dead_code_detector.detect_repository_dead_functions(
            files_data, call_graph
        )

        # Attach results to files
        for file in files_data:
            file["dead_code"]["unused_functions"] = [
                f for f in file["functions"] if f in unused_functions
            ]

        print(f"Repository scan complete. {len(files_data)} files found.")

        complexity_analyzer = ComplexityAnalyzer()
        complexity_metrics = complexity_analyzer.analyze_function(node)
        
        return files_data
 

# This wrapper keeps compatibility with existing tests
def analyze_repository(repo_path: str):
    analyzer = RepoAnalyzer()
    return analyzer.analyze_repository(repo_path)