"""The visual check (M7): screenshots of a built app, compared automatically.

A UI-library migration is largely styling, and the repo's type-check, lint and tests
see almost none of it. The visual check builds the app, takes a screenshot of each page
a human listed (``[visual]`` in ``migrate.toml`` or ``case.toml``) and compares two
captures pixel by pixel:

- in evals, the run against the reference PR's own build (before vs after would mostly
  show the new version's intended look everywhere);
- in a real run, before against after, ranked, for the reviewer.

**A visual difference is not a verdict.** It flags the page, and the files behind it,
as a visual change to review, like M6's snapshots to review, and it is evidence for the
judge. It never changes a file's outcome on its own.

**Where it runs.** The page runs code the repair agent may have written, so the
screenshots are taken only in the Docker sandbox, with the network off. The image is
the pinned Node image plus Debian's Chromium and two font packages, built locally from
``BROWSER_DOCKERFILE`` and tagged by its hash (nothing is pushed to a registry). A repo
with a build script is built with its own command in its own Node image; a repo without
one (the fixtures) is bundled with the Migrator's pinned esbuild. Without Docker the
visual check is skipped and says so.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from migrator.execs import NODE_IMAGES, CommandRunner, DockerRunner, SandboxError

TOOLS_SOURCE = Path(__file__).with_name("tools")
CAPTURE_SCRIPT = Path(__file__).with_name("capture.mjs")
BROWSER_NODE = "20"
# Debian's Chromium (it runs on arm64 too, unlike Google Chrome) and fonts, so text
# renders the same in every capture. No font is fetched at run time: the network is off.
BROWSER_DOCKERFILE = """\
FROM {base}
RUN apt-get update \\
 && apt-get install -y --no-install-recommends chromium fonts-dejavu-core fonts-liberation \\
 && rm -rf /var/lib/apt/lists/*
ENV CHROME_BIN=/usr/bin/chromium
"""


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class VisualPage(_Model):
    """One page to screenshot: a path, then clicks (Playwright selectors) to reach it."""

    name: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    path: str = "/"
    click: list[str] = []
    wait_for: str | None = None
    # The source files behind the page, when known: a difference flags them for review.
    files: list[str] = []


class VisualBackend(_Model):
    """The repo's own mock API server, started next to the built site in the capture
    container (network off): requests under ``proxy`` go to it on ``port``."""

    command: str  # run from the workspace root, e.g. "npm run mock:api"
    port: int = Field(gt=0, lt=65536)
    proxy: list[str]  # path prefixes, e.g. ["/apis", "/system"]


class VisualConfig(_Model):
    """``[visual]``: how to build the app and which pages to look at."""

    pages: list[VisualPage]
    backend: VisualBackend | None = None
    # The repo's own build (a shell command) and where it writes the static site. Leave
    # it out to bundle ``entry`` with the Migrator's esbuild instead.
    build: str | None = None
    out: str = "build"
    entry: str | None = None
    root_id: str = "root"  # the element the bundled entry renders into
    viewport: tuple[int, int] = (1280, 800)
    hide: list[str] = []  # selectors hidden in every capture (ripples, live clocks)
    threshold: float = Field(default=0.001, ge=0, le=1)  # share of pixels that flags a page

    def model_post_init(self, _context: object) -> None:
        if self.build is None and self.entry is None:
            raise ValueError("[visual] needs either build (the repo's own) or entry")
        names = [p.name for p in self.pages]
        if len(set(names)) != len(names):
            raise ValueError("[visual] page names must be unique")


class VisualError(RuntimeError):
    pass


# --------------------------------------------------------------------------- the image


def browser_dockerfile(node: str = BROWSER_NODE) -> str:
    return BROWSER_DOCKERFILE.format(base=NODE_IMAGES[node])


def browser_image_tag(node: str = BROWSER_NODE) -> str:
    digest = hashlib.sha256(browser_dockerfile(node).encode()).hexdigest()[:12]
    return f"migrator-browser:node{node}-{digest}"


def ensure_browser_image(docker: str = "docker", node: str = BROWSER_NODE) -> str:
    """The sandbox image with Chromium, built once from ``BROWSER_DOCKERFILE`` (the
    build itself needs the network: it installs Debian packages)."""
    tag = browser_image_tag(node)
    found = subprocess.run(
        [docker, "image", "inspect", tag], capture_output=True, text=True, check=False
    )
    if found.returncode == 0:
        return tag
    built = subprocess.run(
        [docker, "build", "--tag", tag, "-"],
        input=browser_dockerfile(node),
        capture_output=True,
        text=True,
        check=False,
        timeout=1200,
    )
    if built.returncode != 0:
        raise SandboxError(f"building {tag} failed: {built.stderr.strip()[-800:]}")
    return tag


# --------------------------------------------------------------------------- tools


def ensure_visual_tools(runner: CommandRunner, cache_root: Path | None = None) -> Path:
    """esbuild and playwright-core, installed once (in the sandbox image, so the
    binaries are Linux ones) with the capture script next to them."""
    from migrator.rules import ensure_tools_dir

    target = ensure_tools_dir(TOOLS_SOURCE, "visual", runner, cache_root)
    shutil.copy2(CAPTURE_SCRIPT, target / CAPTURE_SCRIPT.name)
    return target


# --------------------------------------------------------------------------- capture


class PageCapture(_Model):
    name: str
    path: str
    ok: bool
    error: str | None = None
    errors: list[str] = []  # the page's own console errors
    blocked: list[str] = []  # requests to anything but the local server (refused)
    failed: list[str] = []  # "<status> <path>" for every response of 400 or more


class Capture(_Model):
    """One capture of every page: where the screenshots are and what happened."""

    folder: Path
    pages: list[PageCapture]
    built_by: Literal["repo build", "esbuild"]

    def png(self, name: str) -> Path:
        return self.folder / f"{name}.png"


def index_html(root_id: str) -> str:
    return (
        '<!doctype html><html><head><meta charset="utf-8"><title>visual check</title>'
        f'</head><body><div id="{root_id}"></div><script src="app.js"></script></body></html>\n'
    )


def bundle(
    workspace: Path, config: VisualConfig, tools: Path, site: Path, runner: CommandRunner
) -> None:
    """Bundle ``config.entry`` with the pinned esbuild into ``site`` (app.js, index.html)."""
    assert config.entry is not None
    site.mkdir(parents=True, exist_ok=True)
    (site / "index.html").write_text(index_html(config.root_id), "utf-8")
    result = runner.run(
        [
            "node", str(tools / "node_modules" / "esbuild" / "bin" / "esbuild"),
            config.entry, "--bundle", f"--outfile={site / 'app.js'}",
            "--jsx=automatic", "--loader:.js=jsx", "--log-level=warning",
            '--define:process.env.NODE_ENV="production"', "--minify",
        ],
        workspace,
        log_file=site.parent / "bundle.log",
    )  # fmt: skip
    if not result.ok:
        raise VisualError(f"bundling {config.entry} failed: {result.output.strip()[-800:]}")


def capture(
    workspace: Path,
    config: VisualConfig,
    out: Path,
    *,
    build_runner: CommandRunner,
    browser_runner: DockerRunner,
    tools: Path,
) -> Capture:
    """Build the app (its own build, or esbuild) and screenshot every page into ``out``."""
    out.mkdir(parents=True, exist_ok=True)
    with_tools = DockerRunner(
        browser_runner.image,
        read_only=[tools],
        docker=browser_runner.docker,
        limits=browser_runner.limits,
    )
    if config.build is not None:
        built = build_runner.run(config.build, workspace, log_file=out / "build.log")
        if not built.ok:
            raise VisualError(f"`{config.build}` failed; see {out / 'build.log'}")
        site = workspace / config.out
        by: Literal["repo build", "esbuild"] = "repo build"
    else:
        site = out / "site"
        bundle(workspace, config, tools, site, with_tools)
        by = "esbuild"
    if not (site / "index.html").is_file():
        raise VisualError(f"{site} has no index.html; is [visual] out right?")
    shots = out / "shots"
    request = {
        "site": str(site.resolve()),
        "out": str(shots.resolve()),
        "pages": [
            p.model_dump(include={"name", "path", "click", "wait_for"}) for p in config.pages
        ],
        "viewport": list(config.viewport),
        "hide": config.hide,
        "backend": (
            {**config.backend.model_dump(), "cwd": str(workspace.resolve())}
            if config.backend
            else None
        ),
    }
    (out / "capture-input.json").write_text(json.dumps(request, indent=2), "utf-8")
    shots.mkdir(parents=True, exist_ok=True)
    mounts = [tools]
    if config.backend is not None:
        mounts.append(workspace.resolve())  # the backend runs from the workspace
    if not site.resolve().is_relative_to(out.resolve()) and not any(
        site.resolve().is_relative_to(m) for m in mounts
    ):
        mounts.append(site.resolve())
    viewer = (
        with_tools
        if len(mounts) == 1
        else DockerRunner(
            browser_runner.image,
            read_only=mounts,
            docker=browser_runner.docker,
            limits=browser_runner.limits,
        )
    )
    done = viewer.run(
        ["node", str(tools / CAPTURE_SCRIPT.name), str((out / "capture-input.json").resolve())],
        out,
        log_file=out / "capture.log",
        timeout_s=600,
    )
    report = shots / "capture.json"
    if not done.ok or not report.is_file():
        raise VisualError(f"the capture failed; see {out / 'capture.log'}")
    pages = [PageCapture.model_validate(p) for p in json.loads(report.read_text("utf-8"))["pages"]]
    return Capture(folder=shots, pages=pages, built_by=by)
