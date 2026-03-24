import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.analysis.patch_generator import PatchGenerator

original_code = """
def process(arr):
    for i in arr:
        for j in arr:
            if i == j:
                print(i)
"""

improved_code = """
def process(arr):
    seen = set(arr)
    for value in seen:
        print(value)
"""

generator = PatchGenerator()

patch = generator.generate_patch(original_code, improved_code)

print(patch)