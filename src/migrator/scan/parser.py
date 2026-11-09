"""tree-sitter over TS/TSX: the usages of a library in one file, and its comments.

A usage is an import (one per imported name, re-exports included), a JSX element or a
call whose callee is a name imported from a matching module. Closing JSX tags are not
counted, so each element counts once. Not handled yet: ``require()``, dynamic
``import()`` and names used as plain values (``styled(Button)`` counts as a call of
``styled``, not a usage of ``Button``).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from functools import cache
from typing import Literal

import tree_sitter_typescript as tsts
from pydantic import BaseModel, ConfigDict
from tree_sitter import Language, Node, Parser

UsageKind = Literal["import", "jsx", "call"]


class Usage(BaseModel):
    model_config = ConfigDict(frozen=True)

    line: int  # 1-based
    column: int  # 1-based
    kind: UsageKind
    module: str
    symbol: str
    local_name: str
    type_only: bool = False


class Comment(BaseModel):
    model_config = ConfigDict(frozen=True)

    line: int
    text: str


class ParsedFile(BaseModel):
    model_config = ConfigDict(frozen=True)

    usages: list[Usage]
    comments: list[Comment]
    has_syntax_errors: bool


@cache
def _parser(dialect: Literal["ts", "tsx"]) -> Parser:
    lang = tsts.language_typescript() if dialect == "ts" else tsts.language_tsx()
    return Parser(Language(lang))


def dialect_for(path: str) -> Literal["ts", "tsx"]:
    """``.ts`` files need the TypeScript grammar (angle-bracket casts); the rest TSX."""
    return "ts" if path.endswith((".ts", ".mts", ".cts")) else "tsx"


def _text(node: Node | None) -> str:
    return node.text.decode("utf-8", "replace") if node is not None and node.text else ""


def _walk(node: Node) -> Iterator[Node]:
    stack = [node]
    while stack:
        current = stack.pop()
        yield current
        stack.extend(reversed(current.children))


def _source(node: Node) -> str | None:
    source = node.child_by_field_name("source")
    if source is None:
        return None
    fragment = next((c for c in source.children if c.type == "string_fragment"), None)
    return _text(fragment)


def _has_type_keyword(node: Node) -> bool:
    return any(c.type == "type" for c in node.children)


def _default_symbol(module: str, local: str) -> str:
    """``import Button from '@material-ui/core/Button'`` imports ``Button``."""
    parts = module.split("/")
    package_len = 2 if module.startswith("@") else 1
    return parts[-1] if len(parts) > package_len else local


class _Binding(BaseModel):
    module: str
    symbol: str  # "*" for a namespace import


def parse_file(source: bytes, path: str, module_filter: Callable[[str], bool]) -> ParsedFile:
    """Usages of modules accepted by ``module_filter`` in one file, plus all comments."""
    tree = _parser(dialect_for(path)).parse(source)
    root = tree.root_node
    usages: list[Usage] = []
    bindings: dict[str, _Binding] = {}

    def add(
        node: Node, kind: UsageKind, module: str, symbol: str, local: str, type_only: bool
    ) -> None:
        usages.append(
            Usage(
                line=node.start_point.row + 1,
                column=node.start_point.column + 1,
                kind=kind,
                module=module,
                symbol=symbol,
                local_name=local,
                type_only=type_only,
            )
        )

    for stmt in root.children:
        if stmt.type not in ("import_statement", "export_statement"):
            continue
        module = _source(stmt)
        if module is None or not module_filter(module):
            continue
        statement_type_only = _has_type_keyword(stmt)
        if stmt.type == "export_statement":
            for spec in (n for n in _walk(stmt) if n.type == "export_specifier"):
                name = _text(spec.child_by_field_name("name"))
                alias = _text(spec.child_by_field_name("alias")) or name
                add(spec, "import", module, name, alias, statement_type_only)
            continue
        clause = next((c for c in stmt.children if c.type == "import_clause"), None)
        if clause is None:  # side-effect import: import '@material-ui/core/styles'
            add(stmt, "import", module, "*", "", statement_type_only)
            continue
        for child in clause.children:
            if child.type == "identifier":
                local = _text(child)
                symbol = _default_symbol(module, local)
                bindings[local] = _Binding(module=module, symbol=symbol)
                add(child, "import", module, symbol, local, statement_type_only)
            elif child.type == "namespace_import":
                ident = next((c for c in child.children if c.type == "identifier"), None)
                local = _text(ident)
                bindings[local] = _Binding(module=module, symbol="*")
                add(child, "import", module, "*", local, statement_type_only)
            elif child.type == "named_imports":
                for spec in (c for c in child.children if c.type == "import_specifier"):
                    name = _text(spec.child_by_field_name("name"))
                    local = _text(spec.child_by_field_name("alias")) or name
                    type_only = statement_type_only or _has_type_keyword(spec)
                    if not type_only:
                        bindings[local] = _Binding(module=module, symbol=name)
                    add(spec, "import", module, name, local, type_only)

    def reference(node: Node | None) -> tuple[_Binding, str, str] | None:
        """(binding, symbol, local text) when ``node`` names an imported value."""
        if node is None or node.type not in (
            "identifier",
            "member_expression",
            "nested_identifier",
        ):
            return None
        text = _text(node)
        root_name, _, rest = text.partition(".")
        binding = bindings.get(root_name)
        if binding is None:
            return None
        if binding.symbol == "*":
            symbol = rest or "*"
        else:
            symbol = f"{binding.symbol}.{rest}" if rest else binding.symbol
        return binding, symbol, text

    comments: list[Comment] = []
    for node in _walk(root):
        if node.type == "comment":
            comments.append(Comment(line=node.start_point.row + 1, text=_text(node)))
            continue
        if node.type in ("jsx_opening_element", "jsx_self_closing_element"):
            kind: UsageKind = "jsx"
            target = node.child_by_field_name("name")
        elif node.type == "call_expression":
            kind = "call"
            target = node.child_by_field_name("function")
        else:
            continue
        found = reference(target)
        if found is not None and target is not None:
            binding, symbol, text = found
            add(target, kind, binding.module, symbol, text, False)

    usages.sort(key=lambda u: (u.line, u.column, u.kind))
    return ParsedFile(usages=usages, comments=comments, has_syntax_errors=root.has_error)
