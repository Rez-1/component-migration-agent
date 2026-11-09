"""Which team owns a file: CODEOWNERS when the repo has one, else its top-level folder."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

CODEOWNERS_LOCATIONS = ("CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS")
TeamSource = Literal["CODEOWNERS", "folder"]


class OwnerRule(BaseModel):
    model_config = ConfigDict(frozen=True)

    pattern: str
    owners: list[str]


def _pattern_regex(pattern: str) -> re.Pattern[str]:
    """A CODEOWNERS (gitignore-style) pattern as a regex over repo-relative paths."""
    anchored = pattern.startswith("/") or "/" in pattern.rstrip("/")
    body = pattern.strip("/")
    directory = pattern.endswith("/")
    out = []
    i = 0
    while i < len(body):
        if body.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif body.startswith("**", i):
            out.append(".*")
            i += 2
        elif body[i] == "*":
            out.append("[^/]*")
            i += 1
        elif body[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(body[i]))
            i += 1
    prefix = "" if anchored else "(?:.*/)?"
    # A pattern matches the path itself or anything below it (a folder).
    suffix = "/.*" if directory else "(?:/.*)?"
    return re.compile(f"^{prefix}{''.join(out)}{suffix}$")


def parse_codeowners(text: str) -> list[OwnerRule]:
    rules = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        pattern, *owners = line.split()
        rules.append(OwnerRule(pattern=pattern, owners=owners))
    return rules


class Teams:
    def __init__(self, rules: list[OwnerRule] | None):
        self.rules = rules
        self._compiled = [(_pattern_regex(r.pattern), r) for r in rules or []]

    @property
    def source(self) -> TeamSource:
        return "CODEOWNERS" if self.rules is not None else "folder"

    def team_for(self, path: str) -> str:
        if self.rules is None:
            head, sep, _ = path.partition("/")
            return f"{head}/" if sep else "(root)"
        owner = "(unowned)"
        for regex, rule in self._compiled:  # the last matching rule wins
            if regex.match(path):
                owner = " ".join(rule.owners) or "(unowned)"
        return owner


def load_teams(repo: Path) -> Teams:
    for location in CODEOWNERS_LOCATIONS:
        path = repo / location
        if path.is_file():
            return Teams(parse_codeowners(path.read_text("utf-8")))
    return Teams(None)
