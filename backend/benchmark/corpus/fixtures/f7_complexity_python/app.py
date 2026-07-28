"""Fixture: High Cyclomatic Complexity (Python, role=utility, warn>=10)."""


def tangled(a, b, c, d):
    total = 0
    if a > 0:
        total += 1
    if b > 0:
        total += 1
    if c > 0:
        total += 1
    if d > 0:
        total += 1
    if a and b:
        total += 1
    if c or d:
        total += 1
    for i in range(a):
        if i % 2 == 0:
            total += i
    while total < 100:
        total += 1
    try:
        total += int(a)
    except ValueError:
        total += 0
    return total               # TP high_complexity (cc ~13)


def simple(x):
    return x + 1               # decoy: cc 1
