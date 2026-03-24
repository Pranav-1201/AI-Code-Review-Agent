"""
Master test runner for the AI Code Review System.

This script executes all backend test modules sequentially
and prints a clear summary of results.

Usage:
    python backend/tests/run_all_tests.py
"""

import subprocess
import sys
from pathlib import Path


# ---------------------------------------------------------
# Discover test files automatically
# ---------------------------------------------------------

TEST_DIR = Path(__file__).parent

test_files = sorted(TEST_DIR.glob("test_*.py"))

if not test_files:
    print("No test files found.")
    sys.exit(1)


# ---------------------------------------------------------
# Run tests
# ---------------------------------------------------------

passed = []
failed = []

print("\n========================================")
print(" Running AI Code Review System Tests")
print("========================================\n")

for test in test_files:

    print(f"\nRunning {test.name}")
    print("-" * 40)

    result = subprocess.run(
        ["pytest", str(test)],
        text=True
    )

    if result.returncode == 0:
        passed.append(test.name)
    else:
        failed.append(test.name)


# ---------------------------------------------------------
# Summary
# ---------------------------------------------------------

print("\n========================================")
print(" TEST SUMMARY")
print("========================================")

print(f"\nPassed: {len(passed)}")
for t in passed:
    print(f"  ✓ {t}")

print(f"\nFailed: {len(failed)}")
for t in failed:
    print(f"  ✗ {t}")

print("\n========================================")

if failed:
    sys.exit(1)
else:
    sys.exit(0)