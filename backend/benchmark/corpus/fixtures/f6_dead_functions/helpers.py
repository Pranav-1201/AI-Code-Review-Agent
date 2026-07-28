"""Helper module for the dead-functions fixture."""


def used_helper(n):          # decoy: imported+called by main.py
    return n + 1


def orphan():                # TP dead_function (never called anywhere)
    return 0
