
from backend.app.analysis.dead_code_detector import DeadCodeDetector

code = """
import numpy
import os

x = 10
y = 20

def helper():
    print("hello")

print(y)
"""

detector = DeadCodeDetector()

result = detector.analyze(code)

print(result)