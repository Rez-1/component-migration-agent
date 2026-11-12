"""RunFiles: the run folder's snapshots, logs and conversations.

The run folder holds what is too large for the graph state: whole-workspace snapshots
(untouched, Start of Repair, final), command logs, and one conversation per repaired
file. Nothing here is cached: each read goes to disk, so a resumed run sees what the
run before the pause wrote.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from langchain_core.messages import BaseMessage, messages_to_dict

from migrator.checks import FileSet


def save_files(path: Path, files: FileSet) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(files, ensure_ascii=False), "utf-8")
    return str(path)


def load_files(path: Path) -> FileSet:
    if not path.is_file():
        return {}
    data = json.loads(path.read_text("utf-8"))
    return {str(k): str(v) for k, v in data.items()}


def slug(path: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", path).strip("-")


class RunFiles:
    """One run folder (``runs/<run-id>/``, or ``.migrator/runs/<run-id>/``)."""

    def __init__(self, folder: Path):
        self.folder = folder

    @property
    def logs(self) -> Path:
        return self.folder / "logs"

    @property
    def snapshots(self) -> Path:
        return self.folder / "state"

    @property
    def untouched_path(self) -> Path:
        return self.snapshots / "untouched.json"

    @property
    def rules_marker(self) -> Path:
        """Written when Rules start: the codemods are not idempotent (see rules_node)."""
        return self.snapshots / "rules-started"

    @property
    def final_usage_path(self) -> Path:
        return self.snapshots / "final-usage.json"

    def untouched(self) -> FileSet:
        """The workspace the Pre-check verified, before any change."""
        return load_files(self.untouched_path)

    def save_untouched(self, files: FileSet) -> None:
        save_files(self.untouched_path, files)

    def start_of_repair(self) -> FileSet:
        """The workspace as Repair starts: the codemods' changes plus the Migrator's own
        snapshot updates (see ``state.py``)."""
        return load_files(self.snapshots / "after-rules.json")

    def save_start_of_repair(self, files: FileSet) -> None:
        save_files(self.snapshots / "after-rules.json", files)

    def save_final(self, files: FileSet) -> None:
        """The final code, for scoring against a reference PR afterwards (M6)."""
        save_files(self.snapshots / "final.json", files)

    def save_conversation(self, path: str, messages: list[BaseMessage]) -> str:
        """One file's repair conversation; returns its path inside the run folder."""
        conv = self.folder / "repair" / f"{slug(path)}.json"
        conv.parent.mkdir(parents=True, exist_ok=True)
        conv.write_text(
            json.dumps(messages_to_dict(messages), indent=2, ensure_ascii=False), "utf-8"
        )
        return str(conv.relative_to(self.folder))
