"""The visual check's captures and comparison (M7), as the run graph calls them."""

from __future__ import annotations

import hashlib
import shutil
import time
from pathlib import Path
from typing import Any

from migrator.execs import DockerRunner, SandboxError
from migrator.rules import ToolsError, tools_cache_root
from migrator.run.context import RunContext
from migrator.run.state import RunState
from migrator.visual import VisualError, capture, ensure_browser_image, ensure_visual_tools
from migrator.visual.compare import VisualReport, new_page_errors
from migrator.visual.compare import compare as compare_captures
from migrator.workspace import GitError


def visual_capture(ctx: RunContext, workspace: Path, label: str) -> dict[str, Any] | None:
    """Screenshots of the app as ``workspace`` is now (M7), or why there are none; None
    when the repo has no [visual] section. A failure never fails the run."""
    d = ctx.deps
    cfg = d.config.visual
    if cfg is None:
        return None
    if d.sandbox != "docker":
        return {"skipped": "the visual check runs only in the Docker sandbox"}
    cfg = cfg.model_copy(update={"hide": [*d.spec.visual_hide, *cfg.hide]})
    made_out = cfg.build is not None and not (workspace / cfg.out).exists()
    t0 = time.monotonic()
    try:
        browser = DockerRunner(ensure_browser_image())
        tools = ensure_visual_tools(browser, d.tools_cache)
        cap = capture(
            workspace,
            cfg,
            ctx.files.folder / "visual" / label,
            build_runner=d.runner,
            browser_runner=browser,
            tools=tools,
        )
    except (VisualError, SandboxError, ToolsError) as exc:
        d.say("Visual", f"{label}: {exc}")
        return {"skipped": f"the {label} capture failed: {exc}"}
    finally:
        if made_out:  # the repo's build output must not end up in a commit
            shutil.rmtree(workspace / cfg.out, ignore_errors=True)
    ok = sum(p.ok for p in cap.pages)
    d.say(
        "Visual",
        f"{label}: {ok} of {len(cap.pages)} pages ({round(time.monotonic() - t0)} s)",
    )
    return cap.model_dump(mode="json")


def visual_report(ctx: RunContext, state: RunState, finished: bool) -> VisualReport | None:
    """Before against after, page by page, and pages that broke (M7)."""
    cfg = ctx.deps.config.visual
    if cfg is None:
        return None
    before = state.get("visual_before")
    if not before or before.get("skipped"):
        why = (before or {}).get("skipped") or "there is no before capture"
        return VisualReport(skipped=str(why))
    if not finished:
        return VisualReport(skipped="the run stopped before its final verify")
    after = visual_capture(ctx, ctx.workspace(state), "after")
    if not after or after.get("skipped"):
        return VisualReport(skipped=str((after or {}).get("skipped")))
    names = [p.name for p in cfg.pages]
    files = {p.name: p.files for p in cfg.pages}
    comparisons = []
    reference = visual_reference(ctx)
    if reference is not None:
        comparisons.append(
            compare_captures(
                reference,
                Path(after["folder"]),
                names,
                ctx.files.folder / "visual" / "reference-vs-after",
                a_label="the reference PR",
                b_label="this run",
                threshold=cfg.threshold,
                files=files,
            )
        )
    comparisons.append(
        compare_captures(
            Path(before["folder"]),
            Path(after["folder"]),
            names,
            ctx.files.folder / "visual" / "before-vs-after",
            a_label="before",
            b_label="after",
            threshold=cfg.threshold,
            files=files,
        )
    )
    return VisualReport(
        built_by=str(after.get("built_by")),
        comparisons=comparisons,
        new_page_errors=new_page_errors(before["pages"], after["pages"], "after"),
    )


def visual_reference(ctx: RunContext) -> Path | None:
    """For a real-repo eval case: screenshots of the reference PR's own build, made
    once per case and visual config and kept in the cache (M7). None without one."""
    d = ctx.deps
    cfg = d.config.visual
    if cfg is None or d.case is None or d.case.upstream is None or d.mode != "eval":
        return None
    from migrator.evals.upstream import materialize_reference
    from migrator.verify import install

    cfg = cfg.model_copy(update={"hide": [*d.spec.visual_hide, *cfg.hide]})
    try:
        image = ensure_browser_image()
        browser = DockerRunner(image)
        tools = ensure_visual_tools(browser, d.tools_cache)
        key = hashlib.sha256(
            "\0".join(
                [d.case.upstream.reference_head, cfg.model_dump_json(), image, tools.name]
            ).encode()
        ).hexdigest()[:16]
        out = (d.tools_cache or tools_cache_root()) / "visual-reference" / f"{d.case.id}-{key}"
        if (out / "shots" / "capture.json").is_file():
            return out / "shots"
        ref = materialize_reference(d.case, d.tools_cache)
        if not (ref / "node_modules").is_dir():
            d.say("Visual", "installing the reference PR's dependencies (once per case)")
            done = install(d.runner, ref, d.config, frozen=True, log_file=out / "install.log")
            if not done.ok:
                raise VisualError(f"installing the reference failed; see {out / 'install.log'}")
        cap = capture(ref, cfg, out, build_runner=d.runner, browser_runner=browser, tools=tools)
    except (VisualError, SandboxError, ToolsError, GitError, ValueError) as exc:
        d.say("Visual", f"no reference capture: {exc}")
        return None
    d.say("Visual", f"reference PR: {sum(p.ok for p in cap.pages)} of {len(cap.pages)} pages")
    return cap.folder
