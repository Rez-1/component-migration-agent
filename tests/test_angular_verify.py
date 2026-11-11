"""Verify for Angular (M7): the ng build reader and Karma."""

from __future__ import annotations

import json
from pathlib import Path

from migrator.verify.karma import (
    find_karma_config,
    parse_karma_json,
    spec_files_for,
    write_wrapper,
)
from migrator.verify.parsers import parse_ng_build

NG_BUILD = """\
- Generating browser application bundles (phase: setup)...
Error: src/app/tags/tag-list.component.html:4:3 - error NG8001: 'mat-chip-list' is not a known element:
1. If 'mat-chip-list' is an Angular component, then verify that it is part of this module.
2. If 'mat-chip-list' is a Web Component then add 'CUSTOM_ELEMENTS_SCHEMA' to the '@NgModule.schemas' of this component to suppress this message.

4   <mat-chip-list aria-label="Tags">
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

  src/app/tags/tag-list.component.ts:6:16
    6   templateUrl: './tag-list.component.html',
                     ~~~~~~~~~~~~~~~~~~~~~~~~~~~
    Error occurs in the template of component TagListComponent.


Error: src/app/shared/material.module.ts:3:10 - error TS2305: Module '"@angular/material/legacy-chips"' has no exported member 'MatChipsModule'.

3 import { MatChipsModule } from '@angular/material/legacy-chips';
           ~~~~~~~~~~~~~~


Error: Module build failed (from ./node_modules/sass-loader/dist/cjs.js):
SassError: Undefined mixin.
   ╷
12 │   @include mat.legacy-chips-theme($theme);
   │   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
   ╵
  src/styles/theme.scss 12:3  root stylesheet

Error: src/app/tags/tag-list.component.html:4:3 - error NG8001: 'mat-chip-list' is not a known element:
"""


def test_ng_build_errors_are_charged_to_the_template_ts_or_stylesheet() -> None:
    found = parse_ng_build(NG_BUILD, "/ws")
    assert [(f.file, f.line, f.code) for f in found] == [
        ("src/app/tags/tag-list.component.html", 4, "NG8001"),
        ("src/app/shared/material.module.ts", 3, "TS2305"),
        ("src/styles/theme.scss", 12, "sass"),
    ]  # the repeated NG8001 counts once
    assert found[0].message == "'mat-chip-list' is not a known element"
    assert found[2].message == "Undefined mixin."
    assert parse_ng_build("✔ Browser application bundle generation complete.") == []


def test_esbuild_style_prefixes_are_read_too() -> None:
    out = "✘ [ERROR] src/app/a.component.html:2:1 - error NG8002: Can't bind to 'x'"
    [f] = parse_ng_build(out)
    assert (f.file, f.code) == ("src/app/a.component.html", "NG8002")


def karma_report(*specs: dict[str, object], error: bool = False) -> str:
    return json.dumps({"specs": list(specs), "error": error, "exitCode": 1})


SPEC_SOURCES = [
    ("src/app/tags/tag-list.component.spec.ts", "describe('TagListComponent', () => {"),
    ("src/app/home/home.component.spec.ts", 'describe("HomeComponent", () => {'),
]


def exists(path: str) -> bool:
    return path in {"src/app/tags/tag-list.component.ts", "src/app/home/home.component.ts"}


def test_a_failing_spec_is_charged_to_its_component_from_the_stack_or_the_describe() -> None:
    report = karma_report(
        {
            "suite": ["TagListComponent"],
            "description": "shows chips",
            "success": False,
            "log": [
                "Expected 0 to be 3.\n    at UserContext.<anonymous> "
                "(src/app/tags/tag-list.component.spec.ts:31:22)"
            ],
            "console": [],
        },
        {
            "suite": ["HomeComponent", "header"],
            "description": "renders",
            "success": False,
            "log": ["TypeError: Cannot read properties of null (reading 'textContent')"],
            "console": [],
        },
        {
            "suite": ["HomeComponent"],
            "description": "creates",
            "success": True,
            "log": [],
            "console": [],
        },
        {
            "suite": ["HomeComponent"],
            "description": "later",
            "success": True,
            "skipped": True,
            "log": [],
            "console": [],
        },
    )
    failures, totals = parse_karma_json(report, "/ws", exists, SPEC_SOURCES)
    tags, home = failures
    assert (tags.file, tags.test_file, tags.line) == (
        "src/app/tags/tag-list.component.ts",
        "src/app/tags/tag-list.component.spec.ts",
        31,
    )
    assert tags.test_name == "TagListComponent › shows chips"
    assert tags.message == "Expected 0 to be 3."
    assert (home.file, home.test_file) == (
        "src/app/home/home.component.ts",
        "src/app/home/home.component.spec.ts",
    )
    assert (totals.tests_total, totals.tests_passed, totals.tests_failed, totals.tests_skipped) == (
        4,
        1,
        2,
        1,
    )
    assert (totals.suites_total, totals.suites_failed) == (2, 2)


def test_an_unknown_element_logged_in_a_passing_spec_is_a_failure() -> None:
    report = karma_report(
        {
            "suite": ["TagListComponent"],
            "description": "creates",
            "success": True,
            "log": [],
            "console": [
                "'ERROR', 'NG0304: \\'mat-chip-list\\' is not a known element (used in "
                "the \\'TagListComponent\\' component template)'",
                "'ERROR', 'something else'",
            ],
        },
    )
    [f] = parse_karma_json(report, None, exists, SPEC_SOURCES)[0]
    assert "NG0304" in f.message and f.file == "src/app/tags/tag-list.component.ts"


def test_a_karma_error_outside_any_spec_is_one_failure() -> None:
    [f] = parse_karma_json(karma_report(error=True), None, exists)[0]
    assert f.test_name == "(run)" and f.file is None


def test_the_wrapper_loads_the_repo_config_and_adds_headless_chrome_and_the_reporter(
    tmp_path: Path,
) -> None:
    (tmp_path / "karma.conf.js").write_text("module.exports = function (config) {};")
    assert find_karma_config(tmp_path) == "karma.conf.js"
    wrapper, out = write_wrapper(tmp_path, "karma.conf.js", tmp_path / "logs", "verify")
    text = wrapper.read_text()
    assert json.dumps(str((tmp_path / "karma.conf.js").resolve())) in text
    assert "'--no-sandbox'" in text and "singleRun: true" in text
    assert json.dumps(str(out)) in text and "captureConsole: true" in text
    assert wrapper.name == "verify-karma.conf.cjs"


def test_a_narrow_run_includes_the_specs_of_a_component_and_its_template() -> None:
    have = {"src/app/a.component.spec.ts"}
    assert spec_files_for(
        [
            "src/app/a.component.html",
            "src/app/a.component.scss",
            "src/app/b.component.ts",
            "src/app/a.component.spec.ts",
        ],
        lambda p: p in have,
    ) == ["src/app/a.component.spec.ts"]


def test_karma_config_and_the_test_entry_point_are_test_files(tmp_path: Path) -> None:
    from migrator.checks import find_test_files, read_test_rules

    for name in ("karma.conf.js", "src/test.ts", "src/app/a.component.spec.ts", "src/app/a.ts"):
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text("x")
    rules = read_test_rules(tmp_path)
    found = find_test_files(
        {}, ["karma.conf.js", "src/test.ts", "src/app/a.component.spec.ts", "src/app/a.ts"], rules
    )
    assert set(found) == {"karma.conf.js", "src/test.ts", "src/app/a.component.spec.ts"}
