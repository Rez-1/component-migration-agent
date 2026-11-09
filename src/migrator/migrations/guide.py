"""The vendored migration guide, split into sections by heading.

A *section* is one heading at the spec's ``section_level`` (for MUI ``##``: one
component or area); a *change* is one heading at ``change_level`` below it (for MUI
``###``). A change heading that starts with the spec's codemod marker (``✅``) is one
the official codemods already handle.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from migrator.migrations import GuideConfig

_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)")


class GuideChange(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    file: str
    section: str
    title: str
    # "change" for a change heading; "section" for a section with no change headings
    # (troubleshooting entries, intros), which describes no single breaking change.
    kind: Literal["change", "section"]
    codemod_handled: bool
    body: str


def slug(text: str) -> str:
    text = text.replace("`", "").lower()
    return re.sub(r"[^a-z0-9@]+", "-", text).strip("-")


def _plain(title: str) -> str:
    return title.replace("`", "").strip()


def parse_guide_file(name: str, text: str, config: GuideConfig) -> list[GuideChange]:
    """Split one guide file into its changes, in file order.

    A section with no change headings becomes one change of its own, so its text is
    still findable. Headings inside fenced code blocks are ignored.
    """
    stem = Path(name).stem
    changes: list[GuideChange] = []
    section: str | None = None
    title: str | None = None
    body: list[str] = []
    section_had_change = False
    in_fence = False

    def flush() -> None:
        if section is None or section in config.drop_sections:
            return
        if title is None and section_had_change:
            return
        heading = title if title is not None else section
        marker = config.codemod_marker
        handled = bool(marker) and heading.startswith(marker or "")
        clean = _plain(heading.removeprefix(marker or "")) if handled else _plain(heading)
        change_slug = slug(clean) if title is not None else ""
        changes.append(
            GuideChange(
                id=f"{stem}#{slug(section)}" + (f"/{change_slug}" if change_slug else ""),
                file=name,
                section=_plain(section),
                title=clean,
                kind="change" if title is not None else "section",
                codemod_handled=handled,
                body="\n".join(body).strip(),
            )
        )

    for line in text.splitlines():
        if _FENCE.match(line):
            in_fence = not in_fence
        match = None if in_fence else _HEADING.match(line)
        level = len(match.group(1)) if match else 0
        if match and level <= config.section_level:
            flush()
            section = match.group(2) if level == config.section_level else None
            title, body, section_had_change = None, [], False
            continue
        if match and level == config.change_level and section is not None:
            if title is not None or "".join(body).strip():
                flush()
            title, body, section_had_change = match.group(2), [], True
            continue
        body.append(line)
    flush()
    return changes


def load_guide(guide_dir: Path, config: GuideConfig) -> list[GuideChange]:
    changes: list[GuideChange] = []
    for name in config.files:
        changes.extend(parse_guide_file(name, (guide_dir / name).read_text("utf-8"), config))
    return changes


def changes_for_symbol(symbol: str, changes: list[GuideChange]) -> list[GuideChange]:
    """Breaking changes that are about ``symbol``: the change headings of its own
    section (``## Button``), or a change heading that names it as a word
    (``### ✅ Rename fade to alpha``)."""
    word = re.compile(rf"(?<![\w$]){re.escape(symbol)}(?![\w$])")
    return [
        c for c in changes if c.kind == "change" and (c.section == symbol or word.search(c.title))
    ]
