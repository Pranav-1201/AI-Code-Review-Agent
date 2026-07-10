# ==========================================================
# File: symbol_table.py
# Location: backend/app/analysis
#
# Purpose
# ----------------------------------------------------------
# Scope-aware variable -> assignment-source resolver for a
# single module AST. Phase 3 (taint analysis) resolves each
# name it sees at a sink back to the expression that produced
# it; that requires modelling Python's real scoping rules, not
# a dotted-path prefix walk.
#
# Scoping rules implemented (CPython semantics)
# ----------------------------------------------------------
# 1. Closures: a name not found locally is looked up in
#    enclosing FUNCTION scopes, then module, then gives up.
#
# 2. Class scopes are NOT in the lookup chain. A method does
#    not see its class body's names via closure:
#
#        class C:
#            x = 1
#            def m(self):
#                return x      # NameError at runtime
#
#    A lookup that STARTS in the class body does see them.
#
# 3. Comprehensions (list/set/dict/genexp) each get their own
#    scope in Python 3. The iteration variable is local to the
#    comprehension and does NOT leak to the enclosing scope.
#
# 4. The OUTERMOST iterable of a comprehension is evaluated in
#    the ENCLOSING scope, not inside the comprehension scope.
#
# Stdlib-only (ast).
# ==========================================================

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Dict, List, Optional


# Scope kinds that participate in closure lookup.
_CLOSURE_KINDS = frozenset({"module", "function", "lambda", "comprehension"})


@dataclass(frozen=True)
class Symbol:
    """A single binding of `name` at `line` within `scope_id`."""
    name: str
    source_type: str          # Constant | FunctionCall | Parameter | Import | ...
    source_node: ast.AST      # the expression that produced the value
    scope_id: int
    line: int


@dataclass
class Scope:
    id: int
    kind: str                 # module | function | lambda | class | comprehension
    name: str
    parent: Optional[int]
    qualname: str
    symbols: Dict[str, List[Symbol]] = field(default_factory=dict)


def _source_type(node: ast.AST) -> str:
    if isinstance(node, ast.Constant):
        return "Constant"
    if isinstance(node, ast.Call):
        return "FunctionCall"
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        return "Import"
    if isinstance(node, ast.BinOp):
        return "BinOp"
    if isinstance(node, ast.Subscript):
        return "Subscript"
    if isinstance(node, ast.Attribute):
        return "Attribute"
    if isinstance(node, ast.Name):
        return "Name"
    return "Unknown"


class SymbolTable:
    """
    Build with SymbolTable(tree).build(), then resolve names with
    lookup(name, scope_id, at_line=None).

    Scope ids are integers; `qualname_to_scope` maps readable dotted
    paths (e.g. "module.C.m") to those ids for callers and tests.
    """

    def __init__(self, tree: ast.AST) -> None:
        self.tree = tree
        self.scopes: Dict[int, Scope] = {}
        self.qualname_to_scope: Dict[str, int] = {}
        # scope created BY a def/lambda/comprehension node
        self.scope_of_node: Dict[ast.AST, int] = {}
        self._next_id = 0
        self._built = False

    # ------------------------------------------------------
    # Construction
    # ------------------------------------------------------

    def _new_scope(self, kind: str, name: str, parent: Optional[int]) -> int:
        sid = self._next_id
        self._next_id += 1

        if parent is None:
            qualname = name
        else:
            qualname = f"{self.scopes[parent].qualname}.{name}"

        # Disambiguate duplicate qualnames (two comprehensions in one
        # function, or a re-defined function name).
        unique = qualname
        n = 2
        while unique in self.qualname_to_scope:
            unique = f"{qualname}#{n}"
            n += 1

        self.scopes[sid] = Scope(id=sid, kind=kind, name=name,
                                 parent=parent, qualname=unique)
        self.qualname_to_scope[unique] = sid
        return sid

    def _add_symbol(self, scope_id: int, name: str, source_type: str,
                    source_node: ast.AST, line: int) -> None:
        sym = Symbol(name=name, source_type=source_type,
                     source_node=source_node, scope_id=scope_id, line=line)
        bucket = self.scopes[scope_id].symbols.setdefault(name, [])
        bucket.append(sym)
        bucket.sort(key=lambda s: s.line)

    def _bind_target(self, scope_id: int, target: ast.AST,
                     value_node: ast.AST, line: int) -> None:
        """Bind an assignment target, unpacking tuples/lists/starred."""
        if isinstance(target, ast.Name):
            self._add_symbol(scope_id, target.id, _source_type(value_node),
                             value_node, line)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for elt in target.elts:
                self._bind_target(scope_id, elt, value_node, line)
        elif isinstance(target, ast.Starred):
            self._bind_target(scope_id, target.value, value_node, line)
        # ast.Attribute / ast.Subscript targets bind no new local name

    def build(self) -> "SymbolTable":
        module_scope = self._new_scope("module", "module", None)
        self.scope_of_node[self.tree] = module_scope
        self._visit_body(getattr(self.tree, "body", []), module_scope)
        self._built = True
        return self

    # -- statement / expression walkers ---------------------

    def _visit_body(self, body, scope_id: int) -> None:
        for stmt in body:
            self._visit(stmt, scope_id)

    def _visit(self, node: ast.AST, scope_id: int) -> None:
        # --- scope-creating definitions ---
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # The def NAME binds in the ENCLOSING scope.
            self._add_symbol(scope_id, node.name, "FunctionDef", node, node.lineno)
            # Decorators + default values evaluate in the enclosing scope.
            for d in node.decorator_list:
                self._visit_expr(d, scope_id)
            for d in list(node.args.defaults) + [x for x in node.args.kw_defaults if x]:
                self._visit_expr(d, scope_id)

            fn_scope = self._new_scope("function", node.name, scope_id)
            self.scope_of_node[node] = fn_scope
            self._bind_params(node.args, fn_scope)
            self._visit_body(node.body, fn_scope)
            return

        if isinstance(node, ast.ClassDef):
            self._add_symbol(scope_id, node.name, "ClassDef", node, node.lineno)
            for d in node.decorator_list:
                self._visit_expr(d, scope_id)
            for b in node.bases:
                self._visit_expr(b, scope_id)

            cls_scope = self._new_scope("class", node.name, scope_id)
            self.scope_of_node[node] = cls_scope
            self._visit_body(node.body, cls_scope)
            return

        # --- bindings ---
        if isinstance(node, ast.Assign):
            self._visit_expr(node.value, scope_id)
            for t in node.targets:
                self._bind_target(scope_id, t, node.value, node.lineno)
            return

        if isinstance(node, ast.AnnAssign):
            if node.value is not None:
                self._visit_expr(node.value, scope_id)
                self._bind_target(scope_id, node.target, node.value, node.lineno)
            return

        if isinstance(node, ast.AugAssign):
            self._visit_expr(node.value, scope_id)
            self._bind_target(scope_id, node.target, node.value, node.lineno)
            return

        if isinstance(node, (ast.For, ast.AsyncFor)):
            self._visit_expr(node.iter, scope_id)
            self._bind_target(scope_id, node.target, node.iter, node.lineno)
            self._visit_body(node.body, scope_id)
            self._visit_body(node.orelse, scope_id)
            return

        if isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                self._visit_expr(item.context_expr, scope_id)
                if item.optional_vars is not None:
                    self._bind_target(scope_id, item.optional_vars,
                                      item.context_expr, node.lineno)
            self._visit_body(node.body, scope_id)
            return

        if isinstance(node, ast.Import):
            for alias in node.names:
                bound = alias.asname or alias.name.split(".")[0]
                self._add_symbol(scope_id, bound, "Import", node, node.lineno)
            return

        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "*":
                    continue
                bound = alias.asname or alias.name
                self._add_symbol(scope_id, bound, "Import", node, node.lineno)
            return

        if isinstance(node, ast.ExceptHandler):
            if node.name:
                self._add_symbol(scope_id, node.name, "ExceptHandler", node, node.lineno)
            self._visit_body(node.body, scope_id)
            return

        # --- everything else: recurse, handling nested scopes in exprs ---
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.expr):
                self._visit_expr(child, scope_id)
            else:
                self._visit(child, scope_id)

    def _bind_params(self, args: ast.arguments, scope_id: int) -> None:
        all_args = list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs)
        if args.vararg:
            all_args.append(args.vararg)
        if args.kwarg:
            all_args.append(args.kwarg)
        for a in all_args:
            self._add_symbol(scope_id, a.arg, "Parameter", a, a.lineno)

    def _visit_expr(self, node: ast.AST, scope_id: int) -> None:
        """Walk an expression, opening scopes for lambdas/comprehensions."""
        if isinstance(node, ast.Lambda):
            for d in list(node.args.defaults) + [x for x in node.args.kw_defaults if x]:
                self._visit_expr(d, scope_id)
            lam = self._new_scope("lambda", "<lambda>", scope_id)
            self.scope_of_node[node] = lam
            self._bind_params(node.args, lam)
            self._visit_expr(node.body, lam)
            return

        if isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            kindname = {
                ast.ListComp: "<listcomp>", ast.SetComp: "<setcomp>",
                ast.DictComp: "<dictcomp>", ast.GeneratorExp: "<genexpr>",
            }[type(node)]
            comp = self._new_scope("comprehension", kindname, scope_id)
            self.scope_of_node[node] = comp

            for i, gen in enumerate(node.generators):
                # Rule 4: the OUTERMOST iterable is evaluated in the
                # ENCLOSING scope; inner ones inside the comprehension.
                self._visit_expr(gen.iter, scope_id if i == 0 else comp)
                # Rule 3: the target binds INSIDE the comprehension scope.
                self._bind_target(comp, gen.target, gen.iter,
                                  getattr(gen.target, "lineno", node.lineno))
                for cond in gen.ifs:
                    self._visit_expr(cond, comp)

            if isinstance(node, ast.DictComp):
                self._visit_expr(node.key, comp)
                self._visit_expr(node.value, comp)
            else:
                self._visit_expr(node.elt, comp)
            return

        if isinstance(node, ast.NamedExpr):  # walrus binds in enclosing scope
            self._visit_expr(node.value, scope_id)
            self._bind_target(scope_id, node.target, node.value, node.lineno)
            return

        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.expr):
                self._visit_expr(child, scope_id)
            else:
                self._visit(child, scope_id)

    # ------------------------------------------------------
    # Resolution
    # ------------------------------------------------------

    def lookup(self, name: str, scope_id: int,
               at_line: Optional[int] = None) -> Optional[Symbol]:
        """
        Resolve `name` starting at `scope_id`, walking outward through
        enclosing FUNCTION/comprehension scopes to module scope.

        Class scopes are skipped unless the lookup starts there
        (CPython closure semantics).

        If `at_line` is given, return the last binding strictly BEFORE
        that line (static single-assignment approximation).
        """
        if not self._built:
            raise RuntimeError("SymbolTable.build() must be called first")

        current = scope_id
        first = True

        while current is not None:
            scope = self.scopes[current]

            considered = first or scope.kind in _CLOSURE_KINDS
            if considered and name in scope.symbols:
                candidates = scope.symbols[name]
                if at_line is not None:
                    earlier = [s for s in candidates if s.line < at_line]
                    if earlier:
                        return earlier[-1]
                    # bound here but not before at_line -> keep walking outward
                else:
                    return candidates[-1]

            first = False
            current = scope.parent

        return None

    def scope_id_for(self, qualname: str) -> Optional[int]:
        """Look up a scope id by its readable dotted path."""
        return self.qualname_to_scope.get(qualname)

    def names_in(self, scope_id: int) -> List[str]:
        return sorted(self.scopes[scope_id].symbols)

    # ------------------------------------------------------
    # Taint sources (consumed by Phase 3)
    # ------------------------------------------------------

    def get_taint_sources(self) -> List[Symbol]:
        """
        Every symbol that originates outside the module: function
        parameters, plus known external-input expressions.
        """
        out: List[Symbol] = []
        for scope in self.scopes.values():
            for bucket in scope.symbols.values():
                for sym in bucket:
                    if sym.source_type == "Parameter" or _is_external_source(sym.source_node):
                        out.append(sym)
        return out

    def __repr__(self) -> str:  # pragma: no cover
        return f"<SymbolTable scopes={len(self.scopes)}>"


def _is_external_source(node: ast.AST) -> bool:
    """input(), sys.argv, os.getenv/environ.get, request.args/form/json/get_json()."""
    if isinstance(node, ast.Call):
        fn = node.func
        if isinstance(fn, ast.Name) and fn.id == "input":
            return True
        if isinstance(fn, ast.Attribute):
            if fn.attr == "get_json" and isinstance(fn.value, ast.Name) and fn.value.id == "request":
                return True
            if fn.attr == "getenv" and isinstance(fn.value, ast.Name) and fn.value.id == "os":
                return True
            if (fn.attr == "get" and isinstance(fn.value, ast.Attribute)
                    and fn.value.attr == "environ"
                    and isinstance(fn.value.value, ast.Name) and fn.value.value.id == "os"):
                return True
    elif isinstance(node, ast.Attribute):
        if node.attr in ("args", "form", "json") and isinstance(node.value, ast.Name) \
                and node.value.id == "request":
            return True
        if node.attr == "argv" and isinstance(node.value, ast.Name) and node.value.id == "sys":
            return True
    elif isinstance(node, ast.Subscript):
        return _is_external_source(node.value)
    return False
