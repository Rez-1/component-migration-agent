"""Comparing two captures page by page (the visual check, M7).

Pixel by pixel, on the host (the PNGs are data; nothing runs). Two pixels differ when
any channel differs by more than ``TOLERANCE``, which absorbs anti-aliasing noise but
not a colour or a moved edge. Pages of different heights are compared on the taller
canvas, so content that moved down or disappeared counts. Each page gets the share of
pixels that differ, the box around them and a diff image (the second capture, faded,
with the differing pixels in red). Pages are ranked by that share; a page at or above
the configured threshold is flagged as a visual change to review.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageChops
from pydantic import BaseModel

TOLERANCE = 24  # per channel, of 255
PAD = (255, 0, 255)  # canvas outside a shorter page: counts as different


class PageDiff(BaseModel):
    name: str
    share: float  # of the larger canvas's pixels
    pixels: int
    box: tuple[int, int, int, int] | None  # (left, top, right, bottom) of the differences
    size_a: tuple[int, int]
    size_b: tuple[int, int]
    diff_png: str | None  # relative to the comparison folder
    flagged: bool
    files: list[str] = []  # the source files behind the page, from [visual]


class PageMissing(BaseModel):
    name: str
    why: str


class VisualComparison(BaseModel):
    """Two captures compared: which, and every page ranked by how much changed."""

    a: str  # what the first capture is, e.g. "reference PR" or "before"
    b: str  # e.g. "this run" or "after"
    threshold: float
    pages: list[PageDiff]
    missing: list[PageMissing] = []

    @property
    def flagged(self) -> list[PageDiff]:
        return [p for p in self.pages if p.flagged]


def _canvas(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    if img.size == size:
        return img
    canvas = Image.new("RGB", size, PAD)
    canvas.paste(img, (0, 0))
    return canvas


def diff_page(
    a: Path, b: Path, out: Path | None = None
) -> tuple[int, float, tuple[int, int, int, int] | None, tuple[int, int], tuple[int, int]]:
    """(differing pixels, share, box, size a, size b) for two screenshots; writes a diff
    image to ``out`` when they differ."""
    img_a = Image.open(a).convert("RGB")
    img_b = Image.open(b).convert("RGB")
    size = (max(img_a.width, img_b.width), max(img_a.height, img_b.height))
    ca, cb = _canvas(img_a, size), _canvas(img_b, size)
    delta = ImageChops.difference(ca, cb)
    channels = delta.split()
    mask = channels[0].point(lambda v: 255 if v > TOLERANCE else 0)
    for ch in channels[1:]:
        mask = ImageChops.lighter(mask, ch.point(lambda v: 255 if v > TOLERANCE else 0))
    pixels = mask.histogram()[255]
    box = mask.getbbox()
    total = size[0] * size[1]
    if out is not None and pixels:
        faded = Image.blend(cb, Image.new("RGB", size, (255, 255, 255)), 0.7)
        faded.paste(Image.new("RGB", size, (220, 0, 0)), (0, 0), mask)
        out.parent.mkdir(parents=True, exist_ok=True)
        faded.save(out)
    return pixels, (pixels / total if total else 0.0), box, img_a.size, img_b.size


def compare(
    a_dir: Path,
    b_dir: Path,
    names: list[str],
    out: Path,
    *,
    a_label: str,
    b_label: str,
    threshold: float,
    files: dict[str, list[str]] | None = None,
) -> VisualComparison:
    """Compare the pages ``names`` in two capture folders; diff images go to ``out``."""
    pages: list[PageDiff] = []
    missing: list[PageMissing] = []
    for name in names:
        pa, pb = a_dir / f"{name}.png", b_dir / f"{name}.png"
        if not pa.is_file() or not pb.is_file():
            gone = [label for label, p in ((a_label, pa), (b_label, pb)) if not p.is_file()]
            missing.append(PageMissing(name=name, why=f"no screenshot in {', '.join(gone)}"))
            continue
        target = out / f"{name}.diff.png"
        pixels, share, box, size_a, size_b = diff_page(pa, pb, target)
        pages.append(
            PageDiff(
                name=name,
                share=round(share, 6),
                pixels=pixels,
                box=box,
                size_a=size_a,
                size_b=size_b,
                diff_png=target.name if pixels else None,
                flagged=pixels > 0 and share >= threshold,
                files=(files or {}).get(name, []),
            )
        )
    pages.sort(key=lambda p: (-p.share, p.name))
    return VisualComparison(a=a_label, b=b_label, threshold=threshold, pages=pages, missing=missing)


class PageErrors(BaseModel):
    """A page that broke in a capture where it worked before: it failed to load or its
    script threw (a blank page is the usual sign)."""

    name: str
    capture: str  # e.g. "after"
    errors: list[str]


class VisualReport(BaseModel):
    """The scorecard's visual block: what was compared and what to look at.

    Not a verdict: a flagged page is a visual change to review."""

    built_by: str | None = None
    comparisons: list[VisualComparison] = []
    new_page_errors: list[PageErrors] = []
    skipped: str | None = None  # why there is no comparison (no Docker, a failed build)

    @property
    def to_review(self) -> list[str]:
        """Pages to look at: new page errors first, then flagged pages, most changed first."""
        names = [p.name for p in self.new_page_errors]
        for comparison in self.comparisons:
            names += [p.name for p in comparison.flagged]
        return list(dict.fromkeys(names))


def new_page_errors(
    before: list[dict[str, object]], after: list[dict[str, object]], label: str
) -> list[PageErrors]:
    """Pages that load and run cleanly in ``before`` but not in ``after``."""
    clean = {str(p["name"]) for p in before if p.get("ok") and not p.get("errors")}
    out = []
    for page in after:
        broke = not page.get("ok") or bool(page.get("errors"))
        if str(page["name"]) in clean and broke:
            errors = [str(e).splitlines()[0][:300] for e in page.get("errors") or []]  # type: ignore[attr-defined]
            if page.get("error"):
                errors.insert(0, str(page["error"])[:300])
            out.append(
                PageErrors(
                    name=str(page["name"]), capture=label, errors=list(dict.fromkeys(errors))
                )
            )
    return out
