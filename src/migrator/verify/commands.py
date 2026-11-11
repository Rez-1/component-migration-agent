"""Two helpers Verify's commands and the test-runner adapters share: appending
arguments to a command, and spelling a path as it is on disk."""

from __future__ import annotations

import os
from pathlib import Path


def with_args(command: str, args: list[str]) -> str:
    """Append arguments to a command; ``npm run``/``npm test`` need ``--`` first."""
    sep = " -- " if command.startswith("npm ") and " -- " not in command else " "
    return command + sep + " ".join(args)


def real_path(root: Path, rel: str) -> str | None:
    """``rel`` as it is spelled on disk under ``root``, or None if there is no such file.
    macOS's file system ignores case, so asking whether ``month.tsx`` exists says yes when
    only ``Month.tsx`` does; the failure must be charged to ``Month.tsx``, the path every
    file list has (M6, wps: failures charged to ``month.tsx`` were never repaired)."""
    folder, parts = root, []
    for part in Path(rel).parts:
        try:
            names = [e.name for e in os.scandir(folder)]
        except OSError:
            return None
        match = (
            part if part in names else next((n for n in names if n.lower() == part.lower()), None)
        )
        if match is None:
            return None
        parts.append(match)
        folder = folder / match
    return "/".join(parts) if folder.is_file() else None
