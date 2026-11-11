"""The visual check (M7): config, comparison, page errors and the report lines."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from migrator.config import load_case
from migrator.report import _visual_lines, stable_view
from migrator.visual import (
    VisualConfig,
    VisualPage,
    browser_dockerfile,
    browser_image_tag,
    index_html,
)
from migrator.visual.compare import (
    TOLERANCE,
    VisualReport,
    compare,
    diff_page,
    new_page_errors,
)

CASES = Path(__file__).resolve().parent.parent / "evals" / "cases"


def page(
    path: Path,
    *,
    colour: tuple[int, int, int] = (255, 255, 255),
    box: bool = False,
    size: tuple[int, int] = (100, 50),
) -> Path:
    img = Image.new("RGB", size, colour)
    if box:
        ImageDraw.Draw(img).rectangle((10, 10, 19, 19), fill=(0, 0, 255))  # 100 pixels
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    return path


def test_identical_pages_do_not_differ_and_noise_under_the_tolerance_is_ignored(
    tmp_path: Path,
) -> None:
    a = page(tmp_path / "a" / "p.png")
    b = page(tmp_path / "b" / "p.png", colour=(255 - TOLERANCE, 255, 255))
    pixels, share, box, *_ = diff_page(a, b, tmp_path / "d.png")
    assert (pixels, share, box) == (0, 0.0, None)
    assert not (tmp_path / "d.png").exists()


def test_a_changed_region_is_counted_boxed_and_drawn(tmp_path: Path) -> None:
    a = page(tmp_path / "a" / "p.png")
    b = page(tmp_path / "b" / "p.png", box=True)
    pixels, share, box, _, _ = diff_page(a, b, tmp_path / "d.png")
    assert pixels == 100 and share == pytest.approx(100 / 5000)
    assert box == (10, 10, 20, 20)
    assert Image.open(tmp_path / "d.png").getpixel((15, 15)) == (220, 0, 0)


def test_a_taller_page_counts_the_new_area_as_changed(tmp_path: Path) -> None:
    a = page(tmp_path / "a" / "p.png")
    b = page(tmp_path / "b" / "p.png", size=(100, 60))
    pixels, share, _box, size_a, size_b = diff_page(a, b)
    assert pixels == 1000 and share == pytest.approx(1000 / 6000)
    assert (size_a, size_b) == ((100, 50), (100, 60))


def test_pages_are_ranked_flagged_from_the_threshold_and_missing_ones_listed(
    tmp_path: Path,
) -> None:
    for name, changed in (("same", False), ("small", True)):
        page(tmp_path / "a" / f"{name}.png")
        page(tmp_path / "b" / f"{name}.png", box=changed)
    page(tmp_path / "a" / "gone.png")
    c = compare(
        tmp_path / "a",
        tmp_path / "b",
        ["same", "small", "gone"],
        tmp_path / "out",
        a_label="before",
        b_label="after",
        threshold=0.01,
        files={"small": ["src/S.tsx"]},
    )
    assert [p.name for p in c.pages] == ["small", "same"]
    assert [p.name for p in c.flagged] == ["small"] and c.pages[0].files == ["src/S.tsx"]
    assert c.missing[0].name == "gone" and "after" in c.missing[0].why
    strict = compare(
        tmp_path / "a",
        tmp_path / "b",
        ["small"],
        tmp_path / "o2",
        a_label="a",
        b_label="b",
        threshold=0.05,
    )
    assert strict.flagged == []  # 2% is under a 5% threshold


def test_new_page_errors_are_pages_that_worked_before_and_broke_after() -> None:
    before = [
        {"name": "ok", "ok": True, "errors": []},
        {"name": "already-broken", "ok": True, "errors": ["x"]},
        {"name": "crashes", "ok": True, "errors": []},
        {"name": "times-out", "ok": True, "errors": []},
    ]
    after = [
        {"name": "ok", "ok": True, "errors": []},
        {"name": "already-broken", "ok": True, "errors": ["x"]},
        {"name": "crashes", "ok": True, "errors": ["TypeError: no 'dark'\n    at app.js:1"]},
        {"name": "times-out", "ok": False, "error": "Timeout 10000ms", "errors": []},
    ]
    found = new_page_errors(before, after, "after")
    assert [(e.name, e.errors) for e in found] == [
        ("crashes", ["TypeError: no 'dark'"]),
        ("times-out", ["Timeout 10000ms"]),
    ]


def test_the_report_puts_broken_pages_first_and_is_never_a_verdict(tmp_path: Path) -> None:
    page(tmp_path / "a" / "p.png")
    page(tmp_path / "b" / "p.png", box=True)
    c = compare(
        tmp_path / "a",
        tmp_path / "b",
        ["p"],
        tmp_path / "out",
        a_label="before",
        b_label="after",
        threshold=0.001,
    )
    report = VisualReport(
        built_by="esbuild",
        comparisons=[c],
        new_page_errors=new_page_errors(
            [{"name": "q", "ok": True, "errors": []}],
            [{"name": "q", "ok": True, "errors": ["boom"]}],
            "after",
        ),
    )
    assert report.to_review == ["q", "p"]
    lines = _visual_lines(report, task=True)
    assert lines[0] == "- [ ] `q` breaks in the after capture: boom"
    assert lines[1].startswith("- after against before: 1 of 1 pages differ")
    assert lines[2].startswith("  - [ ] `p`: 2.00% of pixels differ (`p.diff.png`)")
    assert _visual_lines(VisualReport(skipped="no Docker"), task=False) == [
        "- Not compared: no Docker"
    ]


def test_the_visual_block_is_not_part_of_the_stable_scorecard() -> None:
    assert stable_view({"meta": {}, "visual": {"skipped": "x"}, "case": "c"}) == {"case": "c"}


def test_visual_config_needs_a_build_or_an_entry_and_unique_pages() -> None:
    with pytest.raises(ValueError, match=r"build .* or entry"):
        VisualConfig(pages=[VisualPage(name="a")])
    with pytest.raises(ValueError, match="unique"):
        VisualConfig(entry="src/index.tsx", pages=[VisualPage(name="a"), VisualPage(name="a")])
    with pytest.raises(ValueError):
        VisualPage(name="Not A Slug")


def test_the_fixture_case_lists_its_pages_and_the_trap_page() -> None:
    case = load_case(CASES / "fixture-mui4" / "case.toml")
    assert case.repo.visual is not None and case.repo.visual.entry == "src/index.tsx"
    account = next(p for p in case.repo.visual.pages if p.name == "account")
    assert "src/screens/Settings.tsx" in account.files  # the visual-only Switch trap


def test_the_browser_image_is_the_pinned_node_image_plus_chromium_and_tagged_by_hash() -> None:
    dockerfile = browser_dockerfile()
    assert dockerfile.startswith("FROM node:20.") and "@sha256:" in dockerfile.splitlines()[0]
    assert "chromium" in dockerfile and "fonts-dejavu-core" in dockerfile
    assert browser_image_tag().startswith("migrator-browser:node20-")
    assert '<div id="app">' in index_html("app")


@pytest.mark.docker
def test_two_captures_of_the_fixture_are_identical(tmp_path: Path) -> None:
    """The check is only useful if capturing the same app twice gives the same pixels."""
    from migrator.execs import DockerRunner
    from migrator.visual import capture, ensure_browser_image, ensure_visual_tools

    case = load_case(CASES / "fixture-mui4" / "case.toml")
    assert case.repo.visual is not None
    cfg = case.repo.visual.model_copy(update={"hide": [".MuiTouchRipple-root"]})
    fixture = Path(__file__).resolve().parent.parent / "fixtures" / "mui4-app"
    runner = DockerRunner(ensure_browser_image())
    tools = ensure_visual_tools(runner)
    one = capture(
        fixture, cfg, tmp_path / "one", build_runner=runner, browser_runner=runner, tools=tools
    )
    two = capture(
        fixture, cfg, tmp_path / "two", build_runner=runner, browser_runner=runner, tools=tools
    )
    assert all(p.ok and not p.errors for p in one.pages)
    names = [p.name for p in cfg.pages]
    same = compare(
        one.folder, two.folder, names, tmp_path / "d", a_label="1", b_label="2", threshold=0.0
    )
    assert [p.pixels for p in same.pages] == [0] * len(names)


def test_a_real_repo_case_builds_with_its_own_command_and_mock_backend() -> None:
    case = load_case(CASES.parent / "m6-cases" / "kubeflow-pipelines" / "case.toml")
    visual = case.repo.visual
    assert visual is not None and visual.build is not None and visual.out == "build"
    assert visual.backend is not None and visual.backend.port == 3001
    assert "/apis" in visual.backend.proxy and "--transpile-only" in visual.backend.command
    assert visual.pages[0].path == "/#/pipelines"  # hash routes
