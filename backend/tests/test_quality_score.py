from app.services.llm_service import analyze_code

code = """
for i in range(10):
    for j in range(10):
        print(i, j)
"""

result = analyze_code(code)

print(result)