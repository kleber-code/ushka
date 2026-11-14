"""Compile-time rewriting that keeps the `Untrusted` mark where CPython drops it.

CPython builds f-strings, ``"...".format()``, ``"..." % (a, b)`` and
``sep.join(items)`` in C, without asking the operands, so a plain
`str` subclass cannot propagate through them. Since Ushka loads the files in
``routes/`` itself, it can compile them through this module, which rewrites
exactly those expressions into calls to small helpers that propagate the
mark. Code outside the rewritten modules (the stdlib, third-party packages)
is untouched, so it keeps its exact semantics.

Rewrites (only inside the compiled module):

==============================  ===========================================
source                          becomes
==============================  ===========================================
``f"a{x!r:>10}b"``              ``G.fstr(("a", G.fmt(x, "r", ">10"), "b"))``
``obj.format(*a, **k)``         ``G.format(obj, *a, **k)``
``obj.join(items)``             ``G.join(obj, items)``
``left % right``                ``G.mod(left, right)``
``str(x)``                      ``G.str_(str, x)``
==============================  ===========================================

Every helper falls back to the original operation when the receiver is not a
`str` (``bytes.join``, ``int % int``, a shadowed ``str``...), so behaviour
only changes in one way: results built from `Untrusted` values stay
`Untrusted`. t-strings (``t"..."``) are left alone; they need no help.
"""

from __future__ import annotations

import ast
import builtins
import sys
import types
from collections.abc import Iterable
from importlib.abc import MetaPathFinder
from importlib.machinery import PathFinder, SourceFileLoader
from pathlib import Path
from string import Formatter
from typing import Any

from .untrusted import Untrusted

__all__ = [
    "HELPER_NAME",
    "compile_source",
    "exec_file",
    "helpers",
    "install",
    "rewrite_tree",
    "uninstall",
]

HELPER_NAME = "__ushka_guard__"
_CONVERSIONS = {-1: "", 115: "s", 114: "r", 97: "a"}


def _first_source(values: Iterable[Any]) -> str | None:
    for value in values:
        if isinstance(value, Untrusted):
            return value.source
    return None


class _Helpers:
    """Runtime side of the rewrite. One shared instance, exposed as `helpers`."""

    @staticmethod
    def fmt(value: Any, conversion: str, spec: str) -> Any:
        if conversion == "r":
            converted: Any = repr(value)
        elif conversion == "a":
            converted = ascii(value)
        elif conversion == "s":
            converted = builtins.str(value)
        else:
            converted = value
        result = format(converted, spec)
        if isinstance(value, Untrusted) and not isinstance(result, Untrusted):
            return Untrusted(result, value.source)
        return result

    @staticmethod
    def fstr(parts: tuple) -> str:
        result = "".join(parts)
        source = _first_source(parts)
        return Untrusted(result, source) if source is not None else result

    @staticmethod
    def join(sep: Any, items: Any) -> Any:
        if not isinstance(sep, str):
            return sep.join(items)
        items = list(items)
        result = builtins.str.join(sep, items)
        source = _first_source([sep, *items])
        return Untrusted(result, source) if source is not None else result

    @staticmethod
    def format(template: Any, *args: Any, **kwargs: Any) -> Any:
        if not isinstance(template, str):
            return template.format(*args, **kwargs)
        result = builtins.str.format(template, *args, **kwargs)
        source = _first_source([template, *args, *kwargs.values()])
        if source is None:
            # Values reached through attribute/index lookups ("{u.name}").
            used = _referenced_fields(template, args, kwargs)
            source = _first_source(used)
        return Untrusted(result, source) if source is not None else result

    @staticmethod
    def mod(left: Any, right: Any) -> Any:
        result = left % right
        if not isinstance(left, str) or not isinstance(result, str):
            return result
        if isinstance(right, tuple):
            values: list = [left, *right]
        elif isinstance(right, dict):
            values = [left, *right.values()]
        else:
            values = [left, right]
        source = _first_source(values)
        if source is not None and not isinstance(result, Untrusted):
            return Untrusted(result, source)
        return result

    @staticmethod
    def str_(fn: Any, *args: Any, **kwargs: Any) -> Any:
        if fn is builtins.str and len(args) == 1 and not kwargs and isinstance(args[0], Untrusted):
            return args[0]
        return fn(*args, **kwargs)


def _referenced_fields(template: str, args: tuple, kwargs: dict) -> list:
    found = []
    formatter = Formatter()
    auto = 0
    try:
        for _, field, _, _ in formatter.parse(template):
            if field is None:
                continue
            if field == "":
                field = builtins.str(auto)
                auto += 1
            obj, _ = formatter.get_field(field, args, kwargs)
            found.append(obj)
    except (KeyError, IndexError, AttributeError, ValueError, TypeError):
        pass
    return found


helpers = _Helpers()


def _helper(attr: str, node: ast.AST) -> ast.Attribute:
    return ast.copy_location(
        ast.Attribute(value=ast.Name(id=HELPER_NAME, ctx=ast.Load()), attr=attr, ctx=ast.Load()),
        node,
    )


class _Rewriter(ast.NodeTransformer):
    def visit_JoinedStr(self, node: ast.JoinedStr) -> ast.AST:
        self.generic_visit(node)
        if not any(isinstance(v, ast.FormattedValue) for v in node.values):
            return node
        parts: list[ast.expr] = []
        for value in node.values:
            if isinstance(value, ast.FormattedValue):
                spec: ast.expr = value.format_spec if value.format_spec is not None else ast.Constant("")
                parts.append(
                    ast.copy_location(
                        ast.Call(
                            func=_helper("fmt", value),
                            args=[value.value, ast.Constant(_CONVERSIONS[value.conversion]), spec],
                            keywords=[],
                        ),
                        value,
                    )
                )
            else:
                parts.append(value)
        return ast.copy_location(
            ast.Call(
                func=_helper("fstr", node),
                args=[ast.Tuple(elts=parts, ctx=ast.Load())],
                keywords=[],
            ),
            node,
        )

    def visit_FormattedValue(self, node: ast.FormattedValue) -> ast.AST:
        # The format spec of a FormattedValue is itself a JoinedStr, but it must
        # stay one: `ast.FormattedValue.format_spec` cannot hold a Call.
        node.value = self.visit(node.value)
        return node

    def visit_BinOp(self, node: ast.BinOp) -> ast.AST:
        self.generic_visit(node)
        if not isinstance(node.op, ast.Mod):
            return node
        return ast.copy_location(
            ast.Call(func=_helper("mod", node), args=[node.left, node.right], keywords=[]),
            node,
        )

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "join":
            if len(node.args) == 1 and not node.keywords:
                return ast.copy_location(
                    ast.Call(func=_helper("join", node), args=[func.value, node.args[0]], keywords=[]),
                    node,
                )
        elif isinstance(func, ast.Attribute) and func.attr == "format":
            return ast.copy_location(
                ast.Call(
                    func=_helper("format", node),
                    args=[func.value, *node.args],
                    keywords=node.keywords,
                ),
                node,
            )
        elif isinstance(func, ast.Name) and func.id == "str":
            return ast.copy_location(
                ast.Call(func=_helper("str_", node), args=[func, *node.args], keywords=node.keywords),
                node,
            )
        return node


def rewrite_tree(tree: ast.Module) -> ast.Module:
    """Applies the taint-preserving rewrite to a parsed module."""
    tree = _Rewriter().visit(tree)
    return ast.fix_missing_locations(tree)


def compile_source(source: str, filename: str) -> types.CodeType:
    """Parses, rewrites and compiles module source code."""
    tree = ast.parse(source, filename=filename)
    return compile(rewrite_tree(tree), filename, "exec", dont_inherit=True)


def exec_file(module: types.ModuleType, path: str | Path) -> None:
    """Executes the file at `path` as `module`, with the rewrite applied."""
    path = Path(path)
    code = compile_source(path.read_text(encoding="utf-8"), str(path))
    module.__dict__[HELPER_NAME] = helpers
    module.__dict__.setdefault("__file__", str(path))
    exec(code, module.__dict__)  # noqa: S102 - this *is* the module loader


# -- import hook ---------------------------------------------------------------


class _GuardLoader(SourceFileLoader):
    """Source loader that applies the rewrite and never touches ``.pyc`` files.

    Bytecode caching is bypassed in both directions: a rewritten module must
    not be cached (it would reference the helper when loaded without the
    hook), and a cached plain module must not be reused (it would skip the
    rewrite).
    """

    def get_code(self, fullname: str) -> types.CodeType:
        path = self.get_filename(fullname)
        return compile_source(self.get_data(path).decode("utf-8"), path)

    def exec_module(self, module: types.ModuleType) -> None:
        module.__dict__[HELPER_NAME] = helpers
        super().exec_module(module)


class _GuardFinder(MetaPathFinder):
    def __init__(self, prefixes: tuple[str, ...]):
        self.prefixes = prefixes

    def _wanted(self, name: str) -> bool:
        return any(name == p or name.startswith(p + ".") for p in self.prefixes)

    def find_spec(self, name, path=None, target=None):
        if not self._wanted(name):
            return None
        spec = PathFinder.find_spec(name, path)
        if spec is not None and isinstance(spec.loader, SourceFileLoader):
            spec.loader = _GuardLoader(spec.loader.name, spec.loader.path)
        return spec


def install(prefixes: Iterable[str]) -> None:
    """Applies the rewrite to every module imported under `prefixes` from now on.

    Call it before importing your own code, e.g. at the top of ``app.py``::

        from ushka.guard import rewrite
        rewrite.install(["myapp"])
        from myapp import views

    Modules that are already imported are not affected. Only your own
    packages should be listed; the stdlib and dependencies keep running
    unmodified.
    """
    prefixes = tuple(p for p in prefixes if p)
    for finder in sys.meta_path:
        if isinstance(finder, _GuardFinder):
            finder.prefixes = tuple(dict.fromkeys(finder.prefixes + prefixes))
            return
    sys.meta_path.insert(0, _GuardFinder(prefixes))


def uninstall() -> None:
    """Removes the import hook installed by `install()`."""
    sys.meta_path[:] = [f for f in sys.meta_path if not isinstance(f, _GuardFinder)]
