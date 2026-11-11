"""Scanning Angular templates and stylesheets (M7)."""

from __future__ import annotations

from pathlib import Path

from migrator.migrations import MIGRATIONS_DIR, load_spec
from migrator.scan import ScanInput, scan
from migrator.scan.assets import inline_template_usages, style_usages, template_usages

TEMPLATE = """\
<!-- <mat-card> in a comment is not a usage -->
<mat-form-field appearance="legacy" class="wide">
  <mat-label>Total</mat-label>
  <input matInput [value]="a < b ? x : y" (blur)="save()">
  <span>{{ total > 3 ? 'big' : 'small' }}</span>
</mat-form-field>
<button mat-raised-button color="primary" [matTooltip]="tip">Go</button>
<div class="x" *matRowDef="let row"></div>
"""


def test_template_elements_and_attributes_with_quotes_and_comments() -> None:
    found = [(u.line, u.kind, u.symbol) for u in template_usages(TEMPLATE)]
    assert found == [
        (2, "element", "mat-form-field"),
        (3, "element", "mat-label"),
        (4, "attribute", "matInput"),
        (7, "attribute", "mat-raised-button"),
        (7, "attribute", "matTooltip"),
        (8, "attribute", "matRowDef"),
    ]
    assert all(u.module == "template" for u in template_usages(TEMPLATE))


def test_an_inline_template_is_found_at_its_line_in_the_ts_file() -> None:
    ts = (
        "import { Component } from '@angular/core';\n"
        "@Component({\n"
        "  selector: 'x',\n"
        "  template: `<mat-chip-list>\n"
        "    <mat-chip>a</mat-chip></mat-chip-list>`,\n"
        "})\nexport class X {}\n"
    )
    assert [(u.line, u.column, u.symbol) for u in inline_template_usages(ts)] == [
        (4, 14, "mat-chip-list"),
        (5, 5, "mat-chip"),
    ]


def test_legacy_mixins_in_a_stylesheet_are_old_usages() -> None:
    scss = (
        "@use '@angular/material' as mat;\n"
        "@include mat.legacy-core();\n"
        "@include mat.card-theme($t);\n"
    )
    [u] = style_usages(scss, [r"\bmat\.(all-)?legacy-"])
    assert (u.line, u.kind, u.symbol) == (2, "style", "mat.legacy-core")
    spec = load_spec(MIGRATIONS_DIR / "angular-material-legacy-to-mdc")
    assert spec.usage.is_old(u.module) and not spec.usage.is_old("mat.card-theme")


def test_the_angular_scan_counts_imports_and_styles_as_old_and_reports_templates(
    tmp_path: Path,
) -> None:
    files = {
        "src/app/app.module.ts": (
            "import { MatLegacyButtonModule as MatButtonModule } from "
            "'@angular/material/legacy-button';\nexport class AppModule {}\n"
        ),
        "src/app/a.component.html": "<button mat-raised-button>Go</button>\n",
        "src/styles.scss": "@include mat.all-legacy-component-themes($theme);\n",
        "src/app/b.component.ts": "export class B {}\n",
    }
    for rel, text in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text)
    spec = load_spec(MIGRATIONS_DIR / "angular-material-legacy-to-mdc")
    report = scan(
        ScanInput(repo=tmp_path, spec=spec, source_globs=spec.source_globs, exclude=spec.exclude)
    )
    by_path = {f.path: f for f in report.files}
    assert sorted(by_path) == [
        "src/app/a.component.html",
        "src/app/app.module.ts",
        "src/styles.scss",
    ]
    assert sorted(report.affected_files()) == ["src/app/app.module.ts", "src/styles.scss"]
    assert [u.symbol for u in by_path["src/app/a.component.html"].template_usages] == [
        "mat-raised-button"
    ]
