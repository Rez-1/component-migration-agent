"""What the Repair and Review stages record about each file (plain data, no LangGraph).

These records live in the run's graph state (as JSON) and feed the scorecard.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

AttemptResult = Literal["passed", "failed", "handed_off", "cost_cap", "error"]
RepairOutcome = Literal["Migrated by agent", "Handed off", "Unmigrated"]
ReviewChoice = Literal["revert", "keep", "edit"]


class AttemptRecord(BaseModel):
    number: int  # 1-based
    model: str
    tool_calls: int = 0
    note: str | None = None  # the agent's one-line run_verify (or hand_off) note
    result: AttemptResult | None = None
    failures_left: int | None = None
    new_failures_elsewhere: list[str] = []  # "file: check code message"
    stop_reason: str | None = None


class FileRepair(BaseModel):
    """One failing file's repair: its attempts, its patch and how it ended."""

    path: str
    outcome: RepairOutcome | None = None  # None while in progress
    reason: str | None = None  # hand-off or Unmigrated reason
    attempts: list[AttemptRecord] = []
    touched: list[str] = []  # files the patch changed (the failing file and local imports)
    patch_lines: dict[str, int] = {}  # changed lines per touched file, against after-Rules
    edits_applied: int = 0
    parse_warnings: int = 0  # prompt v2: applied edits after which the file did not parse
    edits_rejected: dict[str, int] = {}  # guardrail -> count
    escape_hatches_rejected: dict[str, int] = {}  # file -> edits refused for an escape hatch
    review: ReviewChoice | None = None  # the human's (or the eval's) answer at Review
    migrated_by_human: bool = False
    conversation: str | None = None  # run-folder path of the saved conversation
    # A handed-off file's patch is set aside until Review, so the rest of Repair runs
    # without it: the touched files' text with the patch, and as the repair found them.
    set_aside: dict[str, str] = {}
    originals: dict[str, str] = {}
    failures_at_hand_off: list[str] = []
    restored_for_review: bool = False

    @property
    def tool_calls(self) -> int:
        return sum(a.tool_calls for a in self.attempts)


class ReviewAnswer(BaseModel):
    """The typed resume value of the Review interrupt."""

    choice: ReviewChoice
    note: str = ""


class RepairReport(BaseModel):
    """The Repair and Review stages' part of the scorecard."""

    enabled: bool
    files: list[FileRepair] = []
    review_list: list[str] = []  # the run's hand-offs, in order
    stopped_by_cost_cap: bool = False
    cost_cap_reason: str | None = None
    human_changed: list[str] = []  # files changed at Review (Edit, or while paused)

    @property
    def tool_calls(self) -> int:
        return sum(f.tool_calls for f in self.files)

    @property
    def attempts(self) -> int:
        return sum(len(f.attempts) for f in self.files)

    def record(self, path: str) -> FileRepair | None:
        return next((f for f in self.files if f.path == path), None)
