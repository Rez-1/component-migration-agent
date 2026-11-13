"""A run's visual check (M7): the before and after captures, the reference PR's
capture (cached per case), and the report that compares them.

The run calls these from Pre-check (before) and Report (after, and the comparison). A
failure never fails the run: it becomes a ``skipped`` reason in the report.
"""

from __future__ import annotations

import hashlib
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from migrator.execs import CommandRunner, DockerRunner, SandboxError
from migrator.rules import ToolsError, tools_cache_root
from migrator.visual import (
    VisualConfig,
    VisualError,
    capture,
    ensure_browser_image,
    ensure_visual_tools,
)
from migrator.visual.compare import VisualReport, new_page_errors
from migrator.visual.compare import compare as compare_captures
from migrator.workspace import GitError

if TYPE_CHECKING:
    from migrator.config import CaseConfig, ResolvedRepoConfig


@dataclass(frozen=True)
class VisualSetup:
    """What every capture of one run shares."""

    cfg: VisualConfig  # the repo's [visual], with the migration spec's hide rules added
    sandbox: str  # captures run only in the Docker sandbox
    runner: CommandRunner  # builds the app (the run's runner)
    tools_cache: Path | None
    say: Callable[[str, str], None]


def capture_workspace(setup: VisualSetup, workspace: Path, out: Path) -> dict[str, Any]:
    """Screenshots of the app as ``workspace`` is now, into ``out`` (whose name is the
    capture's label), or why there are none."""
    label, cfg, say = out.name, setup.cfg, setup.say
    if setup.sandbox != "docker":
        return {"skipped": "the visual check runs only in the Docker sandbox"}
    made_out = cfg.build is not None and not (workspace / cfg.out).exists()
    t0 = time.monotonic()
    try:
        browser = DockerRunner(ensure_browser_image())
        tools = ensure_visual_tools(browser, setup.tools_cache)
        cap = capture(
            workspace, cfg, out, build_runner=setup.runner, browser_runner=browser, tools=tools
        )
    except (VisualError, SandboxError, ToolsError) as exc:
        say("Visual", f"{label}: {exc}")
        return {"skipped": f"the {label} capture failed: {exc}"}
    finally:
        if made_out:  # the repo's build output must not end up in a commit
            shutil.rmtree(workspace / cfg.out, ignore_errors=True)
    ok = sum(p.ok for p in cap.pages)
    say("Visual", f"{label}: {ok} of {len(cap.pages)} pages ({round(time.monotonic() - t0)} s)")
    return cap.model_dump(mode="json")


def visual_report(
    setup: VisualSetup,
    before: dict[str, Any] | None,
    workspace: Path | None,
    folder: Path,
    reference: Callable[[], Path | None],
) -> VisualReport:
    """Before against after, page by page, and pages that broke; with ``reference``'s
    capture (asked for only once the after capture exists), it against after too.
    ``workspace`` is None when the run stopped before its final verify."""
    cfg = setup.cfg
    if not before or before.get("skipped"):
        why = (before or {}).get("skipped") or "there is no before capture"
        return VisualReport(skipped=str(why))
    if workspace is None:
        return VisualReport(skipped="the run stopped before its final verify")
    after = capture_workspace(setup, workspace, folder / "after")
    if after.get("skipped"):
        return VisualReport(skipped=str(after.get("skipped")))
    names = [p.name for p in cfg.pages]
    files = {p.name: p.files for p in cfg.pages}
    pairs = [(Path(before["folder"]), "before-vs-after", "before", "after")]
    if (ref := reference()) is not None:
        pairs.insert(0, (ref, "reference-vs-after", "the reference PR", "this run"))
    comparisons = [
        compare_captures(
            a,
            Path(after["folder"]),
            names,
            folder / name,
            a_label=a_label,
            b_label=b_label,
            threshold=cfg.threshold,
            files=files,
        )
        for a, name, a_label, b_label in pairs
    ]
    return VisualReport(
        built_by=str(after.get("built_by")),
        comparisons=comparisons,
        new_page_errors=new_page_errors(before["pages"], after["pages"], "after"),
    )


def reference_capture(
    setup: VisualSetup, case: CaseConfig, config: ResolvedRepoConfig
) -> Path | None:
    """Screenshots of a real-repo eval case's reference PR, built once per case and
    visual config and kept in the tools cache. None when the case has no upstream, or
    the capture failed (and says why)."""
    if case.upstream is None:
        return None
    from migrator.evals.upstream import materialize_reference
    from migrator.verify import install

    cfg, say = setup.cfg, setup.say
    try:
        image = ensure_browser_image()
        browser = DockerRunner(image)
        tools = ensure_visual_tools(browser, setup.tools_cache)
        key = hashlib.sha256(
            "\0".join(
                [case.upstream.reference_head, cfg.model_dump_json(), image, tools.name]
            ).encode()
        ).hexdigest()[:16]
        out = (setup.tools_cache or tools_cache_root()) / "visual-reference" / f"{case.id}-{key}"
        if (out / "shots" / "capture.json").is_file():
            return out / "shots"
        ref = materialize_reference(case, setup.tools_cache)
        if not (ref / "node_modules").is_dir():
            say("Visual", "installing the reference PR's dependencies (once per case)")
            done = install(setup.runner, ref, config, frozen=True, log_file=out / "install.log")
            if not done.ok:
                raise VisualError(f"installing the reference failed; see {out / 'install.log'}")
        cap = capture(ref, cfg, out, build_runner=setup.runner, browser_runner=browser, tools=tools)
    except (VisualError, SandboxError, ToolsError, GitError, ValueError) as exc:
        say("Visual", f"no reference capture: {exc}")
        return None
    say("Visual", f"reference PR: {sum(p.ok for p in cap.pages)} of {len(cap.pages)} pages")
    return cap.folder
