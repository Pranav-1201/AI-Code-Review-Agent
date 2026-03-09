from app.services.llm_service import analyze_code

test_code = """
import os

password = "admin123"

def run():
    os.system("rm -rf /")
"""

result = analyze_code(test_code)

print(result)