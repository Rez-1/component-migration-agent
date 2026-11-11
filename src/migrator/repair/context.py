"""What the repair agent is shown about a file, computed without an LLM (ticket #14).

Local imports and importers come from tree-sitter over the workspace; signatures are
the exported declarations with their bodies cut off; the Rules diff and the patch size
are plain ``difflib``.
"""

from __future__ import annotations

import difflib
import re
from collections.abc import Mapping
from pathlib import PurePosixPath

from tree_sitter import Node

from migrator.checks import CODE_EXTENSIONS, resolve_import
from migrator.scan.parser import module_source, node_text, parse_tree

MAX_FULL_LINES = 400  # files up to this long are shown whole
WINDOW = 15  # otherwise, this many lines either side of each failure
MAX_SIGNATURE_CHARS = 300


# An Angular component's own files (M7): `templateUrl: './a.html'`, `styleUrls: [...]`,
# `styleUrl: '...'`.
_COMPONENT_FILE = re.compile(r"""\b(?:templateUrl|styleUrl)\s*:\s*(['"`])(?P<one>[^'"`]+)\1""")
_STYLE_URLS = re.compile(r"\bstyleUrls\s*:\s*\[(?P<list>[^\]]*)\]")
_QUOTED = re.compile(r"""(['"`])([^'"`]+)\1""")
ANGULAR_ASSETS = (".html", ".scss", ".sass", ".css", ".less")


def component_files(path: str, text: str, files: Mapping[str, str]) -> list[str]:
    """The template and stylesheets an Angular component's decorator names, if they exist."""
    names = [m.group("one") for m in _COMPONENT_FILE.finditer(text)]
    for m in _STYLE_URLS.finditer(text):
        names += [q.group(2) for q in _QUOTED.finditer(m.group("list"))]
    folder = PurePosixPath(path).parent
    found = []
    for name in names:
        rel = PurePosixPath(*(folder / name).parts)
        resolved = _normalise(rel.as_posix())
        if resolved in files and resolved not in found:
            found.append(resolved)
    return found


def _normalise(path: str) -> str:
    parts: list[str] = []
    for part in path.split("/"):
        if part == "..":
            if parts:
                parts.pop()
        elif part not in ("", "."):
            parts.append(part)
    return "/".join(parts)


def owning_components(asset: str, files: Mapping[str, str]) -> list[str]:
    """The components whose decorator names this template or stylesheet."""
    return sorted(
        other
        for other, text in files.items()
        if other.endswith(".ts")
        and ("templateUrl" in text or "styleUrl" in text)
        and asset in component_files(other, text, files)
    )


def local_imports(path: str, files: Mapping[str, str]) -> list[str]:
    """The local files ``path`` imports directly (relative imports that resolve). For an
    Angular component also its template and stylesheets; for a template or stylesheet,
    the component that owns it, that component's other files and the files that import
    it (its NgModule, where an unknown element is fixed) (M7)."""
    text = files.get(path)
    if text is None:
        return []
    if path.endswith(ANGULAR_ASSETS):
        found = []
        for owner in owning_components(path, files):
            found += [owner, *component_files(owner, files[owner], files), *importers(owner, files)]
        return sorted({f for f in found if f != path})
    if not path.endswith(CODE_EXTENSIONS):
        return []
    found = [f for f in component_files(path, text, files) if f != path]
    tree = parse_tree(text.encode("utf-8"), path)
    for stmt in tree.root_node.children:
        if stmt.type not in ("import_statement", "export_statement"):
            continue
        spec = module_source(stmt)
        target = resolve_import(path, spec, files) if spec else None
        if target is not None and target != path and target not in found:
            found.append(target)
    return sorted(found)


def importers(path: str, files: Mapping[str, str]) -> dict[str, str]:
    """The files that import ``path`` directly, each with its import statement."""
    out: dict[str, str] = {}
    for other, text in sorted(files.items()):
        if other == path or not other.endswith(CODE_EXTENSIONS):
            continue
        tree = parse_tree(text.encode("utf-8"), other)
        for stmt in tree.root_node.children:
            if stmt.type not in ("import_statement", "export_statement"):
                continue
            spec = module_source(stmt)
            if spec and resolve_import(other, spec, files) == path:
                out[other] = " ".join(node_text(stmt).split())
    return out


def imported_names(statement: str) -> str:
    """``import { a, b } from './x'`` -> ``a, b`` (the clause, for the Used-by list)."""
    m = re.match(r"(?:import|export)\s+(?:type\s+)?(.*?)\s+from\s", statement)
    clause = m.group(1) if m else statement
    return clause.strip().strip("{}").strip()


def _squash(text: str) -> str:
    text = " ".join(text.split())
    if len(text) > MAX_SIGNATURE_CHARS:
        text = text[: MAX_SIGNATURE_CHARS - 1] + "…"
    return text


def _until(node: Node, child: Node | None, prefix: str = "") -> str:
    """The text of ``node`` up to where ``child`` starts (all of it without a child)."""
    raw = node.text or b""
    if child is None:
        return prefix + raw.decode("utf-8", "replace")
    cut = raw[: child.start_byte - node.start_byte].decode("utf-8", "replace")
    return prefix + cut.rstrip().rstrip("=").rstrip()


_WITH_BODY = frozenset(
    {
        "function_declaration",
        "generator_function_declaration",
        "class_declaration",
        "abstract_class_declaration",
    }
)


def signatures(path: str, text: str) -> list[str]:
    """Exported names and their types, bodies cut off: ``export const theme: Theme``."""
    tree = parse_tree(text.encode("utf-8"), path)
    out: list[str] = []
    for stmt in tree.root_node.children:
        if stmt.type != "export_statement":
            continue
        decl = stmt.child_by_field_name("declaration")
        if decl is None:  # export { a, b }, export default x, re-exports
            out.append(_squash(node_text(stmt)))
            continue
        if decl.type in _WITH_BODY:
            out.append(_squash(_until(decl, decl.child_by_field_name("body"), "export ")))
        elif decl.type == "lexical_declaration":
            kind = decl.children[0].type if decl.children else "const"
            for declarator in decl.named_children:
                if declarator.type != "variable_declarator":
                    continue
                value = declarator.child_by_field_name("value")
                if value is not None and value.type == "arrow_function":
                    body = value.child_by_field_name("body")
                    head = _until(declarator, body, f"export {kind} ")
                    out.append(_squash(head if head.endswith("=>") else head + " =>"))
                elif value is not None and value.type == "call_expression":
                    callee = node_text(value.child_by_field_name("function"))
                    head = _until(declarator, value, f"export {kind} ")
                    out.append(_squash(f"{head} = {callee}(…)"))
                else:
                    out.append(_squash(_until(declarator, value, f"export {kind} ")))
        else:  # interfaces, type aliases, enums: the declaration is the signature
            out.append(_squash(node_text(stmt)))
    return out


def numbered(text: str, start: int = 1, end: int | None = None) -> str:
    lines = text.splitlines()
    end = len(lines) if end is None else min(end, len(lines))
    width = len(str(end))
    return "\n".join(f"{i:>{width}}  {lines[i - 1]}" for i in range(start, end + 1))


def file_view(text: str, failure_lines: list[int]) -> tuple[str, str]:
    """The file for the first message: whole up to 400 lines, else ±15 around failures.

    Returns (heading suffix, numbered text).
    """
    total = len(text.splitlines())
    if total <= MAX_FULL_LINES or not failure_lines:
        return f"{total} lines", numbered(text)
    spans: list[tuple[int, int]] = []
    for line in sorted(set(failure_lines)):
        lo, hi = max(1, line - WINDOW), min(total, line + WINDOW)
        if spans and lo <= spans[-1][1] + 1:
            spans[-1] = (spans[-1][0], max(hi, spans[-1][1]))
        else:
            spans.append((lo, hi))
    parts = [numbered(text, lo, hi) for lo, hi in spans]
    shown = ", ".join(f"{lo}–{hi}" for lo, hi in spans)
    return f"lines {shown} of {total}; `read_file` for the rest", "\n   …\n".join(parts)


def unified_diff(path: str, before: str | None, after: str | None) -> str:
    a = (before or "").splitlines(keepends=True)
    b = (after or "").splitlines(keepends=True)
    lines = difflib.unified_diff(a, b, f"a/{path}", f"b/{path}", n=1)
    return "".join(line if line.endswith("\n") else line + "\n" for line in lines)


class PatchSize:
    """How much a patch changes a file, against the Rules stage's version of it."""

    def __init__(self, before: str, after: str):
        a, b = before.splitlines(), after.splitlines()
        self.lines_before = len(a)
        changed = added = removed = 0
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(
            None, a, b, autojunk=False
        ).get_opcodes():
            if tag == "equal":
                continue
            changed += max(i2 - i1, j2 - j1)
            removed += i2 - i1
            added += j2 - j1
        self.changed = changed
        self.added = added
        self.removed = removed

    @property
    def share(self) -> float:
        return self.changed / max(self.lines_before, 1)

    def describe(self) -> str:
        return f"+{self.added} −{self.removed} lines ({round(self.share * 100)}% of the file)"


def is_code(path: str) -> bool:
    return PurePosixPath(path).name.endswith(CODE_EXTENSIONS)
