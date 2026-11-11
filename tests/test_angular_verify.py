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


def test_leftovers_are_old_imports_old_mixins_and_optionally_codemod_todos(
    tmp_path: Path,
) -> None:
    from migrator.config import LeftoverCheck
    from migrator.verify.leftovers import find_leftovers

    files = {
        "src/app/a.module.ts": (
            "import { MatLegacyButtonModule as MatButtonModule } from "
            "'@angular/material/legacy-button';\n"
            "import { MatCardModule } from '@angular/material/card';\n"
        ),
        "src/styles.scss": (
            "@use '@angular/material' as mat;\n"
            "@include mat.legacy-button-theme($theme);\n"
            "@include mat.card-theme($theme);\n"
            "/* TODO(mdc-migration): The following rule targets internal classes of button "
            "that may no longer apply for the MDC version. */\n"
        ),
        "src/app/a.component.spec.ts": "import { X } from '@angular/material/legacy-chips';\n",
        "src/app/b.ts": "export const ok = 1;\n",
    }
    for rel, text in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text)
    check = LeftoverCheck(
        old_modules=["^@angular/material/legacy-"],
        old_styles=[r"\bmat\.(all-)?legacy-"],
        source_globs=["src/**/*.ts", "src/**/*.scss"],
        exclude=["**/*.spec.ts"],
    )
    found = find_leftovers(tmp_path, check)
    assert [(f.file, f.line, f.code, f.message) for f in found] == [
        (
            "src/app/a.module.ts",
            1,
            "leftover-import",
            "still imports @angular/material/legacy-button",
        ),
        ("src/styles.scss", 2, "leftover-style", "still uses mat.legacy-button-theme"),
    ]
    assert all(f.source == "migration" for f in found)
    with_todos = check.model_copy(update={"todo_markers": ["TODO(mdc-migration)"]})
    todo = find_leftovers(tmp_path, with_todos, only=["src/styles.scss"])[-1]
    assert todo.code == "codemod-todo"
    assert todo.message.startswith("Codemod TODO: TODO(mdc-migration): The following rule")


def test_a_template_can_be_repaired_with_its_component_and_the_module_that_declares_it() -> None:
    from migrator.repair.context import local_imports

    files = {
        "src/app/tags/tag-list.component.ts": (
            "import { Component } from '@angular/core';\nimport { util } from '../util';\n"
            "@Component({ selector: 'x', templateUrl: './tag-list.component.html',\n"
            "  styleUrls: ['./tag-list.component.scss', '../shared.scss'] })\n"
            "export class TagListComponent {}"
        ),
        "src/app/tags/tag-list.component.html": "<mat-chip-list></mat-chip-list>",
        "src/app/tags/tag-list.component.scss": ".a{}",
        "src/app/shared.scss": ".b{}",
        "src/app/util.ts": "export const util = 1;",
        "src/app/app.module.ts": (
            "import { TagListComponent } from './tags/tag-list.component';\n"
            "export class AppModule {}"
        ),
    }
    assert local_imports("src/app/tags/tag-list.component.ts", files) == [
        "src/app/shared.scss",
        "src/app/tags/tag-list.component.html",
        "src/app/tags/tag-list.component.scss",
        "src/app/util.ts",
    ]
    assert local_imports("src/app/tags/tag-list.component.html", files) == [
        "src/app/app.module.ts",
        "src/app/shared.scss",
        "src/app/tags/tag-list.component.scss",
        "src/app/tags/tag-list.component.ts",
    ]


def test_codemod_todos_are_found_in_templates_and_stylesheets_with_any_marker(
    tmp_path: Path,
) -> None:
    from migrator.rules import find_codemod_todos

    after = {
        "src/a.scss": ".x {}\n/* TODO(mdc-migration): The following rule targets internal "
        "classes of button that may no longer apply for the MDC version. */\n",
        "src/a.html": "<mat-slider>\n<!-- TODO: The 'tickInterval' property no longer exists -->\n",
        "src/a.ts": "// TODO(mdc-migration): check\nexport const a = 1; // TODOS are not markers\n",
    }
    for rel, text in after.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text)
    todos = find_codemod_todos(
        {"src/a.ts": b"export const a = 1;\n"},
        tmp_path,
        sorted(after),
        ["TODO(mdc-migration)", "TODO: The '"],
    )
    assert [(t.file, t.line) for t in todos] == [
        ("src/a.html", 2),
        ("src/a.scss", 2),
        ("src/a.ts", 1),
    ]


def test_angular_guardrails_allow_templates_and_styles_and_block_its_configs_and_hatches() -> None:
    from migrator.repair.guardrails import added_escape_hatches, check_target

    allowed = ["src/app/a.component.html", "src/app/a.component.scss"]
    for rel in allowed:
        assert check_target(rel, "src/app/a.component.ts", allowed, {}) is None
    for rel in ("angular.json", "karma.conf.js", "proxy.conf.json"):
        blocked = check_target(rel, "src/app/a.component.ts", [rel], {})
        assert blocked is not None and blocked.guardrail == "config"
    module_before = "@NgModule({ declarations: [A] })\nexport class M {}\n"
    module_after = "import { NO_ERRORS_SCHEMA } from '@angular/core';\n" + module_before.replace(
        "declarations: [A]", "declarations: [A], schemas: [NO_ERRORS_SCHEMA]"
    )
    assert added_escape_hatches("src/app/m.module.ts", module_before, module_after) == [
        "`NO_ERRORS_SCHEMA`"
    ]
    assert added_escape_hatches(
        "src/app/a.component.html", "<p>{{ x.y }}</p>", "<p>{{ $any(x).y }}</p>"
    ) == ["a template `$any(...)` cast"]
    assert added_escape_hatches("src/a.scss", ".a{}", "::ng-deep .mat-mdc-button{}") == []


def test_a_leftover_is_described_to_the_agent_as_not_migrated_yet() -> None:
    from migrator.repair.prompt import describe_failure, failure_elsewhere
    from migrator.verify.parsers import Failure

    f = Failure(
        source="migration",
        file="src/a.ts",
        line=3,
        code="leftover-import",
        message="still imports @angular/material/legacy-button",
    )
    assert describe_failure(f, "src/a.ts") == (
        "**Not migrated yet**, line 3: still imports @angular/material/legacy-button"
    )
    assert failure_elsewhere(f, {}).startswith(
        "Not migrated yet leftover-import, `src/a.ts` line 3"
    )
