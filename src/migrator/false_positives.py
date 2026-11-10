"""Codemod false positives (M6): undo a codemod's change to the repo's own component.

The official codemods match JSX by name. OpossumUI has its own ``IconButton`` wrapper,
and ``preset-safe`` added ``size="large"`` to every ``<IconButton>`` it saw, the wrapper
included; the wrapper has no such prop, so five files stopped type-checking. A codemod
can't know a name is the repo's own; the import in the file says so.

After the codemod steps, every JSX element whose opening tag a codemod changed is
looked up by its tag's import in that file. When the name comes from the repo's own
code (not from the migrating library's old or new modules, which the migration spec
names, and not from an installed package), the codemod's change to that tag is undone.
Each undo is listed as a codemod false positive. No LLM.

Elements are paired before and after by their position among same-named elements in
the file (the codemods change props, they don't add or remove elements); a file where
the counts differ is left alone. Calls are not handled: no codemod in the MUI spec
rewrites a call on a local name.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable

from pydantic import BaseModel

from migrator.scan.parser import module_source, node_text, parse_tree, walk

_ELEMENTS = ("jsx_opening_element", "jsx_self_closing_element")


class CodemodFalsePositive(BaseModel):
    file: str
    line: int  # 1-based, in the codemods' output
    element: str
    imported_from: str
    reverted: str  # the codemod's version of the tag, now undone
    kept: str  # the tag as it was before the codemods


def _imports(tree_root: object) -> dict[str, str]:
    """Local name -> module, for every import in the file."""
    out: dict[str, str] = {}
    for stmt in tree_root.children:  # type: ignore[attr-defined]
        if stmt.type != "import_statement":
            continue
        module = module_source(stmt)
        if not module:
            continue
        for node in walk(stmt):
            if node.type == "import_specifier":
                alias = node.child_by_field_name("alias") or node.child_by_field_name("name")
                out[node_text(alias)] = module
            elif (
                node.type == "identifier"
                and node.parent is not None
                and (node.parent.type == "import_clause")
            ):
                out[node_text(node)] = module
            elif node.type == "namespace_import":
                ident = next((c for c in node.children if c.type == "identifier"), None)
                if ident is not None:
                    out[node_text(ident)] = module
    return out


Tag = tuple[str, int, int, int]  # (root name, start byte, end byte, line)


def _tags(source: bytes, path: str) -> tuple[dict[str, str], list[Tag], list[tuple[int, int]]]:
    """(imports, each element's opening tag, the byte span of every JSX element)."""
    root = parse_tree(source, path).root_node
    tags: list[Tag] = []
    spans: list[tuple[int, int]] = []
    for node in walk(root):
        if node.type in ("jsx_element", "jsx_self_closing_element"):
            spans.append((node.start_byte, node.end_byte))
        if node.type in _ELEMENTS:
            name = node.child_by_field_name("name")
            if name is not None:
                tags.append(
                    (node_text(name).split(".")[0], node.start_byte, node.end_byte,
                     node.start_point.row + 1)
                )  # fmt: skip
    return _imports(root), tags, spans


def _own_text(source: bytes, start: int, end: int, spans: list[tuple[int, int]]) -> bytes:
    """A tag's bytes with any JSX nested inside it (in a prop such as ``endIcon={<X/>}``)
    replaced by a marker, so only the tag's own props are compared."""
    out, i = [], start
    for s, e in sorted(spans):
        if start < s and e <= end and s >= i:
            out += [source[i:s], b"\0"]
            i = e
    out.append(source[i:end])
    return b"".join(out)


def _nested(spans: list[tuple[int, int]], start: int, end: int) -> list[tuple[int, int]]:
    """The outermost JSX spans strictly inside [start, end)."""
    inner = sorted((s, e) for s, e in spans if start < s and e <= end)
    out: list[tuple[int, int]] = []
    for s, e in inner:
        if not out or s >= out[-1][1]:
            out.append((s, e))
    return out


def _restore(
    before: bytes,
    bs: int,
    be: int,
    b_spans: list[tuple[int, int]],
    after: bytes,
    as_: int,
    ae: int,
    a_spans: list[tuple[int, int]],
) -> bytes | None:
    """The tag as it was before the codemods, but with each JSX element nested in its
    props as the codemods left it (those elements are judged on their own)."""
    b_in, a_in = _nested(b_spans, bs, be), _nested(a_spans, as_, ae)
    if len(b_in) != len(a_in):
        return None
    out, i = [], bs
    for (s, e), (s2, e2) in zip(b_in, a_in, strict=True):
        out += [before[i:s], after[s2:e2]]
        i = e
    out.append(before[i:be])
    return b"".join(out)


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def revert_false_positives(
    path: str,
    before: str,
    after: str,
    is_library: Callable[[str], bool],
    packages: Iterable[str],
) -> tuple[str, list[CodemodFalsePositive]]:
    """``after`` with the codemods' changes to the repo's own components undone."""
    if before == after:
        return after, []
    deps = set(packages)
    b_bytes, a_bytes = before.encode("utf-8"), after.encode("utf-8")
    _b_imports, b_tags, b_spans = _tags(b_bytes, path)
    a_imports, a_tags, a_spans = _tags(a_bytes, path)

    def own(name: str) -> str | None:
        module = a_imports.get(name)
        if module is None or is_library(module):
            return None
        package = (
            module.split("/")[0] if not module.startswith("@") else "/".join(module.split("/")[:2])
        )
        return None if package in deps else module

    by_name_b: dict[str, list[tuple[int, int, int]]] = {}
    for name, s, e, line in b_tags:
        by_name_b.setdefault(name, []).append((s, e, line))
    by_name_a: dict[str, list[tuple[int, int, int]]] = {}
    for name, s, e, line in a_tags:
        by_name_a.setdefault(name, []).append((s, e, line))

    edits: list[tuple[int, int, bytes]] = []
    found: list[CodemodFalsePositive] = []
    for name, a_list in by_name_a.items():
        module = own(name)
        b_list = by_name_b.get(name, [])
        if module is None or len(a_list) != len(b_list):
            continue
        for (as_, ae, aline), (bs, be, _bline) in zip(a_list, b_list, strict=True):
            a_tag, b_tag = a_bytes[as_:ae], b_bytes[bs:be]
            if _own_text(a_bytes, as_, ae, a_spans) == _own_text(b_bytes, bs, be, b_spans):
                continue  # unchanged, or changed only inside nested JSX
            restored = _restore(b_bytes, bs, be, b_spans, a_bytes, as_, ae, a_spans)
            if restored is None:
                continue  # nested JSX doesn't pair up: leave the tag as the codemod wrote it
            # Only the tag itself: an element's children are separate elements.
            edits.append((as_, ae, restored))
            found.append(
                CodemodFalsePositive(
                    file=path,
                    line=aline,
                    element=name,
                    imported_from=module,
                    reverted=_squash(a_tag.decode("utf-8", "replace"))[:300],
                    kept=_squash(b_tag.decode("utf-8", "replace"))[:300],
                )
            )
    if not edits:
        return after, []
    out = a_bytes
    for s, e, text in sorted(edits, reverse=True):
        out = out[:s] + text + out[e:]
    return out.decode("utf-8"), sorted(found, key=lambda f: f.line)
