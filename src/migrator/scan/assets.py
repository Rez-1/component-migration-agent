"""Usages in Angular templates and stylesheets (M7).

Most Angular Material usage lives outside TypeScript: elements and attributes in
templates (``<mat-form-field>``, ``<button mat-raised-button>``, ``matInput``) and theme
mixins in stylesheets (``@include mat.legacy-button-theme``).

Templates are read with a small tokenizer, not a full parser: it finds start tags,
respects quoted attribute values (so a ``<`` or ``{{ }}`` inside a binding is harmless)
and skips comments. That is all the scan needs: which library elements and attributes
a template uses, and where. A template element alone doesn't say whether it is legacy
or MDC (the NgModule that imports it does), so template usages are reported but don't
make a file affected; old usages come from imports and stylesheets.

(The Angular tree-sitter grammar on PyPI-less git, v0.9.2, builds without its external
scanner and can't be loaded, which is why this is a tokenizer: M7 notes.)
"""

from __future__ import annotations

import re
from collections.abc import Iterator

from migrator.scan.parser import Usage

TEMPLATE_EXTENSIONS = (".html", ".htm")
STYLE_EXTENSIONS = (".scss", ".sass", ".css", ".less")
_TAG_NAME = re.compile(r"[A-Za-z][\w:.-]*")
_ATTR_NAME = re.compile(r"[^\s\"'>/=]+")
# `template: \`...\`` in a @Component decorator.
_INLINE_TEMPLATE = re.compile(r"\btemplate\s*:\s*`")


def _line_col(text: str, index: int) -> tuple[int, int]:
    line = text.count("\n", 0, index) + 1
    return line, index - (text.rfind("\n", 0, index) + 1) + 1


def _attr_symbol(name: str) -> str:
    """``[matTooltip]`` / ``(matSortChange)`` / ``*matRowDef`` -> the plain name."""
    return name.strip("[]()*#@").removeprefix("attr.").split(".")[0]


def start_tags(text: str) -> Iterator[tuple[int, str, list[tuple[int, str]]]]:
    """(offset, tag name, [(offset, attribute name)]) for every start tag."""
    i, n = 0, len(text)
    while True:
        i = text.find("<", i)
        if i < 0 or i + 1 >= n:
            return
        if text.startswith("<!--", i):
            end = text.find("-->", i + 4)
            i = n if end < 0 else end + 3
            continue
        m = _TAG_NAME.match(text, i + 1)
        if m is None:  # `</x>`, `< b` in text, `<!doctype>`
            i += 1
            continue
        tag, j = m.group(0), m.end()
        attrs: list[tuple[int, str]] = []
        while j < n:
            ch = text[j]
            if ch == ">":
                j += 1
                break
            if ch.isspace() or ch == "/":
                j += 1
                continue
            if ch in "\"'":  # a stray quote: skip its string
                close = text.find(ch, j + 1)
                j = n if close < 0 else close + 1
                continue
            a = _ATTR_NAME.match(text, j)
            if a is None:
                j += 1
                continue
            attrs.append((j, a.group(0)))
            j = a.end()
            while j < n and text[j].isspace():
                j += 1
            if j < n and text[j] == "=":
                j += 1
                while j < n and text[j].isspace():
                    j += 1
                if j < n and text[j] in "\"'":
                    close = text.find(text[j], j + 1)
                    j = n if close < 0 else close + 1
                else:
                    v = _ATTR_NAME.match(text, j)
                    j = v.end() if v else j
        yield i, tag, attrs
        i = j


def template_usages(text: str, prefix: str = "mat", base: tuple[int, int] = (1, 1)) -> list[Usage]:
    """Library elements and attributes in one template. ``base`` is where the template
    starts in its file (an inline template's position in the .ts file)."""
    found: list[Usage] = []

    def at(index: int) -> tuple[int, int]:
        line, col = _line_col(text, index)
        return (base[0] + line - 1, col + (base[1] - 1 if line == 1 else 0))

    for offset, tag, attrs in start_tags(text):
        if tag.startswith(f"{prefix}-"):
            line, col = at(offset)
            found.append(
                Usage(
                    line=line,
                    column=col,
                    kind="element",
                    module="template",
                    symbol=tag,
                    local_name=tag,
                )
            )
        for a_offset, name in attrs:
            symbol = _attr_symbol(name)
            if symbol.startswith(f"{prefix}-") or re.match(rf"{prefix}[A-Z]", symbol):
                line, col = at(a_offset)
                found.append(
                    Usage(
                        line=line,
                        column=col,
                        kind="attribute",
                        module="template",
                        symbol=symbol,
                        local_name=name,
                    )
                )
    return found


def inline_template_usages(text: str, prefix: str = "mat") -> list[Usage]:
    """Usages in ``template: `...``` strings of a TypeScript file, at their real lines."""
    found: list[Usage] = []
    for m in _INLINE_TEMPLATE.finditer(text):
        start = m.end()
        end = text.find("`", start)
        if end < 0:
            break
        found += template_usages(text[start:end], prefix, _line_col(text, start))
    return found


def style_usages(text: str, patterns: list[str]) -> list[Usage]:
    """Old-version stylesheet usages: one per line matching an ``old_styles`` pattern."""
    compiled = [re.compile(p) for p in patterns]
    found: list[Usage] = []
    for number, line in enumerate(text.splitlines(), start=1):
        for pattern in compiled:
            if m := pattern.search(line):
                token = re.match(r"[\w.$@-]+", line[m.start() :])
                symbol = token.group(0) if token else line.strip()
                found.append(
                    Usage(
                        line=number,
                        column=m.start() + 1,
                        kind="style",
                        module=symbol,
                        symbol=symbol,
                        local_name=symbol,
                    )
                )
                break
    return found
