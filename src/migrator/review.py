"""The Review stage's human side: one hand-off at a time, behind a small interface.

The graph pauses with one ``interrupt()`` per hand-off and resumes with a typed
``ReviewAnswer``. Whoever answers implements ``Reviewer``: the Rich loop below for the
CLI (a Textual UI can replace it without touching the graph), or ``AutoReviewer`` for
evals, CI and ``--no-review``, which always answers Revert.
"""

from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.syntax import Syntax

from migrator.repair.records import ReviewAnswer


class ReviewPayload(BaseModel):
    """What the Review interrupt shows about one hand-off (JSON-serialisable)."""

    path: str
    reason: str
    attempts: list[str]  # one line per attempt
    failures: list[str]  # the file's failures now
    diff: str  # the agent's patch against the Rules version ("" when there is none)
    workspace: str
    hashes: dict[str, str]  # code files' hashes when the run paused here
    remaining: int  # hand-offs still to review after this one


class Reviewer(Protocol):
    def review(self, payload: ReviewPayload) -> ReviewAnswer | None:
        """The answer for one hand-off, or None to pause the run here."""
        ...


class AutoReviewer:
    """Evals, CI and ``--no-review``: every hand-off is reverted, nothing prompts."""

    def review(self, payload: ReviewPayload) -> ReviewAnswer:
        return ReviewAnswer(choice="revert", note="automatic (no review)")


def open_editor(path: Path) -> None:
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vi"
    subprocess.run([*shlex.split(editor), str(path)], check=False)


class RichReviewer:
    """The CLI's review loop: show the hand-off, ask Revert / Keep / Edit / quit."""

    def __init__(self, console: Console | None = None):
        self.console = console or Console()

    def review(self, payload: ReviewPayload) -> ReviewAnswer | None:
        c = self.console
        c.rule(f"[bold]Hand-off: {payload.path}")
        c.print(f"[bold]Why:[/] {payload.reason}")
        for line in payload.attempts:
            c.print(f"  {line}")
        if payload.failures:
            c.print("[bold]Failures now:[/]")
            for f in payload.failures:
                c.print(f"  - {f}")
        if payload.diff:
            c.print(Panel(Syntax(payload.diff, "diff", word_wrap=True), title="The agent's patch"))
        else:
            c.print("The repair agent left no patch on this file.")
        c.print(
            f"{payload.remaining} more hand-off(s) after this one. "
            "[bold]r[/]evert (default) · [bold]k[/]eep · [bold]e[/]dit in $EDITOR · "
            "[bold]q[/]uit and resume later"
        )
        choice = Prompt.ask("Choice", choices=["r", "k", "e", "q"], default="r", console=c)
        if choice == "q":
            return None
        if choice == "e":
            open_editor(Path(payload.workspace) / payload.path)
            return ReviewAnswer(choice="edit")
        return ReviewAnswer(choice="revert" if choice == "r" else "keep")
