import os

SUPPORTED_EXTENSIONS = (".py", ".cpp", ".js", ".java")


def analyze_repository(repo_path: str):
    """
    Scan a repository and return all supported code files.
    This function ONLY collects files. Analysis happens later in the pipeline.
    """

    files_data = []

    for root, dirs, files in os.walk(repo_path):

        for file in files:

            if file.endswith(SUPPORTED_EXTENSIONS):

                path = os.path.join(root, file)

                try:
                    with open(path, "r", encoding="utf-8", errors="ignore") as f:
                        code = f.read()

                    files_data.append({
                        "file_name": file,
                        "file_path": path,
                        "content": code
                    })

                except Exception as e:
                    print(f"Failed to read {path}: {e}")

    print(f"Repository scan complete. {len(files_data)} files found.")

    return files_data