# ==========================================================
# File: backend/validation/phase2_validation.py
# Purpose: Chunk 1 (Phase 2 - Semantic Intelligence) harness.
#
# Run:  python backend/validation/phase2_validation.py
# Exit: 0 if every check passes, 1 otherwise.
#
# Deliberately over-weights the edge cases the roadmap flagged
# as hard and therefore likely to be undertested:
#   - closure + comprehension + class-skip scoping (symbol_table)
#   - the __init__.py re-export whitelist in the import graph
#     (cycle detection AND unused-import detection)
# Each check prints the observed values it asserts on.
# ==========================================================

from __future__ import annotations

import ast
import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from backend.app.analysis.ast_parser import parse_module
from backend.app.analysis.symbol_table import SymbolTable
from backend.app.analysis.cohesion_analyzer import analyze_cohesion, lcom4
from backend.app.analysis.call_graph import (
    build_import_graph, detect_circular_imports, detect_unused_imports,
)

_RESULTS: list[tuple[str, bool, str]] = []


def check(item_id: str, description: str):
    def wrap(fn):
        print(f"\n[{item_id}] {description}")
        try:
            detail = fn()
            _RESULTS.append((item_id, True, detail or ""))
            print(f"    PASS  {detail or ''}")
        except AssertionError as e:
            _RESULTS.append((item_id, False, str(e)))
            print(f"    FAIL  {e}")
        except Exception as e:
            _RESULTS.append((item_id, False, f"{type(e).__name__}: {e}"))
            print(f"    ERROR {type(e).__name__}: {e}")
        return fn
    return wrap


def _st(code: str) -> SymbolTable:
    return SymbolTable(ast.parse(code)).build()


# ==========================================================
# ParentTracker wiring
# ==========================================================

@check("P2-parent", "parse_module() attaches .parent to every node; root parent is None")
def _parent():
    tree = parse_module("def f(x):\n    return x + 1\n")
    assert tree is not None
    assert tree.parent is None, "module root parent must be None"
    missing = [type(n).__name__ for n in ast.walk(tree)
               if n is not tree and not hasattr(n, "parent")]
    assert not missing, f"nodes missing .parent: {missing}"
    node = [n for n in ast.walk(tree) if isinstance(n, ast.Name)][0]
    hops, cur = 0, node
    while getattr(cur, "parent", None) is not None:
        cur = cur.parent
        hops += 1
    assert cur is tree, "walking parents must reach the module root"
    assert parse_module("def broken(:\n") is None, "SyntaxError must return None"
    return f"all nodes annotated; Name->root in {hops} hops; syntax error -> None"


# ==========================================================
# Symbol table - the hard scoping edge cases
# ==========================================================

@check("P2-closure", "closure: nested function resolves an enclosing function local")
def _closure():
    st = _st("def outer():\n    secret = 1\n    def inner():\n        return secret\n")
    inner = st.scope_id_for("module.outer.inner")
    sym = st.lookup("secret", inner)
    assert sym is not None, "inner() must resolve enclosing `secret` via closure"
    assert sym.scope_id == st.scope_id_for("module.outer")
    return f"secret resolved from scope {sym.scope_id} (module.outer)"


@check("P2-classskip", "class scope is skipped by closure but visible when lookup starts there")
def _classskip():
    st = _st("class C:\n    x = 1\n    def m(self):\n        return x\n")
    method = st.scope_id_for("module.C.m")
    cls = st.scope_id_for("module.C")
    assert st.lookup("x", method) is None, \
        "a method must NOT see class-body `x` via closure (would be NameError at runtime)"
    assert st.lookup("x", cls) is not None, \
        "a lookup starting in the class body DOES see `x`"
    return "method: x=None (correct), class body: x=found (correct)"


@check("P2-comprehension", "comprehension target is local to the comp and does not leak")
def _comprehension():
    st = _st("def f(items):\n    r = [y for y in items]\n    return r\n")
    fscope = st.scope_id_for("module.f")
    comp = st.scope_id_for("module.f.<listcomp>")
    assert comp is not None, "comprehension must get its own scope"
    assert st.lookup("y", comp) is not None, "`y` is bound inside the comprehension"
    assert st.lookup("y", fscope) is None, "`y` must NOT leak into the enclosing function"
    return "y in comp=found, y in f=None (no leak)"


@check("P2-comp-outer-iter", "outermost comprehension iterable is evaluated in the enclosing scope")
def _comp_outer():
    st = _st("def f(data):\n    return [x for x in data if x]\n")
    comp = st.scope_id_for("module.f.<listcomp>")
    d = st.lookup("data", comp)
    assert d is not None and d.scope_id == st.scope_id_for("module.f"), \
        "outer iterable `data` must resolve to the enclosing function scope"
    return "data resolves to module.f (enclosing), as CPython evaluates it"


@check("P2-ssa", "at_line returns the last binding strictly before the line")
def _ssa():
    st = _st("def f():\n    v = 1\n    v = 2\n    return v\n")
    fs = st.scope_id_for("module.f")
    assert st.lookup("v", fs, at_line=3).line == 2, "before line 3 -> the line-2 binding"
    assert st.lookup("v", fs).line == 3, "no at_line -> latest binding"
    return "at_line=3 -> line 2; latest -> line 3"


@check("P2-taint-src", "taint sources = parameters + external inputs (request.args, input(), ...)")
def _taint():
    code = ("def h(user_input):\n"
            "    a = request.args\n"
            "    b = input()\n"
            "    c = os.getenv('X')\n"
            "    return (a, b, c)\n")
    st = _st(code)
    names = sorted(s.name for s in st.get_taint_sources())
    assert names == ["a", "b", "c", "user_input"], f"got {names}"
    return f"sources={names}"


# ==========================================================
# Cohesion / LCOM4
# ==========================================================

@check("P2-lcom4", "LCOM4: split class -> 2 components, cohesive class -> 1, shared-os.path -> 2")
def _lcom():
    split = ("class S:\n"
             "    def a(self): self.x = 1\n"
             "    def b(self): return self.x\n"
             "    def c(self): self.y = 1\n"
             "    def d(self): return self.y\n")
    coh = ("class C:\n"
           "    def a(self): self.x = 1\n"
           "    def b(self): return self.x\n")
    trap = ("import os\n"
            "class T:\n"
            "    def a(self): return os.path.join('a')\n"
            "    def b(self): return os.path.join('b')\n")

    def cls(src):
        return next(n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.ClassDef))

    s, c, t = lcom4(cls(split)), lcom4(cls(coh)), lcom4(cls(trap))
    assert s == 2, f"split class LCOM4 should be 2, got {s}"
    assert c == 1, f"cohesive class LCOM4 should be 1, got {c}"
    assert t == 2, f"two methods sharing only os.path are NOT cohesive; got {t}"
    return f"split={s}, cohesive={c}, shared-os.path={t}"


@check("P2-size-gate", "size flag needs BOTH >500 lines AND cohesion <0.40 (Flask sessions.py guard)")
def _sizegate():
    tangled = "".join(f"def f{i}(a{i}):\n    return a{i}\n\n" for i in range(8)) + "\n" * 520
    cohesive = ("".join(f"def g{i}(reg):\n    reg.append({i})\n    return reg\n\n"
                        for i in range(8)) + "\n" * 520)
    short = "".join(f"def h{i}(a{i}):\n    return a{i}\n\n" for i in range(8))

    rt = analyze_cohesion(tangled, "tangled.py")
    rc = analyze_cohesion(cohesive, "cohesive.py")
    rs = analyze_cohesion(short, "short.py")

    assert rt.should_flag_size, f"long+incoherent must flag (lines={rt.line_count}, coh={rt.module_cohesion})"
    assert not rc.should_flag_size, f"long+cohesive must NOT flag (coh={rc.module_cohesion})"
    assert not rs.should_flag_size, f"short file must NOT flag (lines={rs.line_count})"
    return (f"tangled({rt.line_count}L,{rt.module_cohesion:.2f})=FLAG, "
            f"cohesive({rc.module_cohesion:.2f})=ok, short({rs.line_count}L)=ok")


# ==========================================================
# Import graph - the __init__.py re-export whitelist
# ==========================================================

@check("P2-cycle", "detect_circular_imports finds a real a<->b cycle")
def _cycle():
    sources = {
        "pkg/a.py": "from pkg import b\n",
        "pkg/b.py": "from pkg import a\n",
    }
    cycles = detect_circular_imports(build_import_graph(sources))
    flat = {m for cyc in cycles for m in cyc}
    assert cycles, "a genuine two-module import cycle must be reported"
    assert "pkg.a" in flat and "pkg.b" in flat, f"cycle should involve pkg.a and pkg.b: {cycles}"
    return f"cycle reported: {cycles[0]}"


@check("P2-init-whitelist", "__init__.py re-export edges do NOT create a false cycle")
def _init_whitelist():
    sources = {
        "pkg/__init__.py": "from pkg.core import Engine\n",
        "pkg/core.py": "class Engine:\n    pass\n",
    }
    cycles = detect_circular_imports(build_import_graph(sources))
    assert cycles == [], f"__init__ re-export must not be a cycle, got {cycles}"

    sources2 = dict(sources)
    sources2["pkg/a.py"] = "from pkg import b\n"
    sources2["pkg/b.py"] = "from pkg import a\n"
    cycles2 = detect_circular_imports(build_import_graph(sources2))
    flat2 = {m for cyc in cycles2 for m in cyc}
    assert "pkg.a" in flat2 and "pkg.b" in flat2, \
        f"real cycle must still be caught alongside an __init__: {cycles2}"
    return f"__init__ re-export -> no cycle; real a<->b still caught: {cycles2}"


@check("P2-unused-init", "unused-import detection whitelists __init__.py re-exports")
def _unused_init():
    mod_src = "import os\nimport sys\nprint(sys.argv)\n"   # os unused, sys used
    edges = build_import_graph({"m.py": mod_src})["m.py"]
    unused = detect_unused_imports(ast.parse(mod_src), edges, "m.py")
    assert [e.importee for e in unused] == ["os"], \
        f"only `os` should be unused: {[e.importee for e in unused]}"

    init_edges = build_import_graph({"pkg/__init__.py": "import os\n"})["pkg/__init__.py"]
    init_unused = detect_unused_imports(ast.parse("import os\n"), init_edges, "pkg/__init__.py")
    assert init_unused == [], f"__init__ re-export must not be flagged unused: {init_unused}"
    return "module: os flagged; __init__: os whitelisted"


@check("P2-alias", "unused-import detection is alias-aware (Fix F: `import numpy as np`)")
def _alias():
    used_src = "import numpy as np\nprint(np.array([1]))\n"
    e1 = build_import_graph({"a.py": used_src})["a.py"]
    assert detect_unused_imports(ast.parse(used_src), e1, "a.py") == [], \
        "aliased import that IS used must not be flagged"

    unused_src = "import numpy as np\nprint(1)\n"
    e2 = build_import_graph({"b.py": unused_src})["b.py"]
    got = [e.alias for e in detect_unused_imports(ast.parse(unused_src), e2, "b.py")]
    assert got == ["np"], f"aliased import that is NOT used must be flagged by alias: {got}"
    return "used alias np -> ok; unused alias np -> flagged"


def main() -> int:
    print("=" * 62)
    print("Phase 2 validation - symbol table, cohesion, import graph")
    print("=" * 62)
    passed = sum(1 for _, ok, _ in _RESULTS if ok)
    total = len(_RESULTS)
    print("\n" + "=" * 62)
    print(f"RESULT: {passed}/{total} checks passed")
    for item_id, ok, _ in _RESULTS:
        print(f"  [{'PASS' if ok else 'FAIL'}] {item_id}")
    print("=" * 62)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
