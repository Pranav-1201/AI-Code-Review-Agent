"""Fixture: Dead Functions (interprocedural). Cross-module reachability."""
from helpers import used_helper


def entry():
    return used_helper(3)


def _never_called(x):        # TP dead_function (never referenced anywhere)
    return x * 2


if __name__ == "__main__":
    entry()
