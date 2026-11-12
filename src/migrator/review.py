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
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.syntax import Syntax

from migrator.checks import read_files
from migrator.repair.records import FileRepair, ReviewAnswer
from migrator.verify import Failure
from migrator.workspace import hash_file


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


def code_hashes(workspace: Path) -> dict[str, str]:
    """Hashes of the workspace's code files (the same set the cheating checks read)."""
    return {p: hash_file(workspace / p) for p in sorted(read_files(workspace))}


def changed_files(before: dict[str, str], now: dict[str, str]) -> list[str]:
    """Code files whose hash differs between two ``code_hashes``, sorted."""
    return sorted(p for p in now.keys() | before.keys() if now.get(p) != before.get(p))


# The narrow verify of a human's edit: the files to check -> (the file's failures, new
# failures elsewhere, the run's known failures after it).
NarrowVerify = Callable[[list[str]], tuple[list[Failure], list[Failure], list[Failure]]]


@dataclass
class ReviewResult:
    """What one answer at Review comes to; the run applies it."""

    record: FileRepair  # the hand-off's repair record, with the answer in it
    done: bool  # the hand-off leaves the review queue (an edit that still fails stays)
    revert: list[str] = field(default_factory=list)  # put back as before the agent's patch
    known_failures: list[Failure] | None = None  # after an edit's narrow verify
    note: str | None = None  # for the run's log


def apply_answer(
    payload: ReviewPayload,
    answer: ReviewAnswer,
    record: FileRepair,
    human_changed: list[str],
    narrow_verify: NarrowVerify,
) -> ReviewResult:
    """Revert undoes the agent's patch, except in files a human changed while the run
    was paused (theirs wins); Keep keeps it, still handed off; Edit checks the human's
    edit with the narrow verify, and a clean one makes the file migrated by a human."""
    record = record.model_copy(deep=True)
    record.review = answer.choice
    if answer.choice == "revert":
        revert = [rel for rel in record.touched if rel not in human_changed]
        record.touched = [rel for rel in record.touched if rel in human_changed]
        return ReviewResult(record, done=True, revert=revert)
    if answer.choice == "keep":
        return ReviewResult(record, done=True)
    left, elsewhere, known = narrow_verify(sorted({*record.touched, *human_changed}))
    if not left and not elsewhere:
        record.migrated_by_human = True
        return ReviewResult(
            record, done=True, known_failures=known, note=f"{payload.path}: fixed by a human"
        )
    still = f"{payload.path}: still {len(left) + len(elsewhere)} failures after the edit"
    return ReviewResult(record, done=False, known_failures=known, note=still)


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
