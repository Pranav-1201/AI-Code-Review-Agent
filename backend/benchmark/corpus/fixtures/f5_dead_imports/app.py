"""Fixture: Dead Imports. Unused imports (TP) vs alias/used imports (decoys)."""
import os                              # TP dead_import (unused)
import sys                             # decoy: used below
import json as j                      # decoy: used as j (alias-aware)
from math import sqrt                  # TP dead_import (unused)
from collections import OrderedDict    # decoy: used below


def use():
    print(sys.argv)
    data = j.dumps({"a": 1})
    od = OrderedDict()
    return data, od
