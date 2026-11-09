from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
from pydantic import ValidationError

from migrator.migrations import (
    CodemodStep,
    MigrationSpec,
    UnknownMigrationError,
    find_spec,
    load_spec,
)
from migrator.migrations.guide import changes_for_symbol, load_guide, parse_guide_file


def test_mui_spec_loads_with_the_decided_step_order(spec: MigrationSpec) -> None:
    assert spec.id == "mui@4->mui@5"
    kinds = [s.kind for s in spec.rule_steps]
    assert kinds == [
        "install",
        "codemod",
        "codemod",
        "codemod",
        "codemod",
        "format",
        "dependencies",
        "install",
    ]
    codemods = [s.name for s in spec.rule_steps if isinstance(s, CodemodStep)]
    assert codemods == ["preset-safe", "variant-prop", "link-underline-hover", "box-sx-prop"]
    assert spec.guide.tag == "v5.18.0"
    assert spec.tools_dir().joinpath("package-lock.json").is_file()


def test_dependency_map_pins_are_exact(spec: MigrationSpec) -> None:
    pins = {name: v for entry in spec.dependency_map for name, v in entry.new.items()}
    assert pins["@mui/material"] == "5.18.0"
    assert all(v[0].isdigit() for v in pins.values()), "no ranges such as ^5"


def test_codemod_tool_is_pinned_to_9_4_0(spec: MigrationSpec) -> None:
    import json

    package = json.loads(spec.tools_dir().joinpath("package.json").read_text())
    assert package["dependencies"] == {"@mui/codemod": "9.4.0"}


def test_usage_patterns(spec: MigrationSpec) -> None:
    assert spec.usage.is_old("@material-ui/core/styles")
    assert spec.usage.is_new("@mui/material")
    assert not spec.usage.is_old("react")


def test_find_spec_unknown() -> None:
    with pytest.raises(UnknownMigrationError, match="mui@5 to mui@6"):
        find_spec("mui@5", "mui@6")


def test_a_codemod_listed_twice_is_rejected(spec: MigrationSpec, tmp_path: Path) -> None:
    data = tomllib.loads(spec.folder.joinpath("migration.toml").read_text("utf-8"))
    data["rule_steps"].append(data["rule_steps"][1])
    with pytest.raises(ValidationError, match="exactly once"):
        MigrationSpec.model_validate(data)


def test_unknown_step_kind_is_rejected(spec: MigrationSpec) -> None:
    data = tomllib.loads(spec.folder.joinpath("migration.toml").read_text("utf-8"))
    data["rule_steps"].append({"kind": "deploy"})
    with pytest.raises(ValidationError):
        MigrationSpec.model_validate(data)


def test_load_spec_sets_folder(spec: MigrationSpec) -> None:
    again = load_spec(spec.folder)
    assert again.folder == spec.folder


GUIDE = """\
## Material UI v5 migration

- links

## Button

Intro text.

### ✅ Remove default color prop

Body one.

### Remove span and label

```md
## Not a heading
```

Body two.

## Troubleshooting entry about makeStyles

Text.
"""


def test_guide_split_by_heading_level(spec: MigrationSpec) -> None:
    changes = parse_guide_file("v5-component-changes.md", GUIDE, spec.guide)
    ids = [c.id for c in changes]
    assert ids == [
        "v5-component-changes#button",
        "v5-component-changes#button/remove-default-color-prop",
        "v5-component-changes#button/remove-span-and-label",
        "v5-component-changes#troubleshooting-entry-about-makestyles",
    ]
    assert [c.codemod_handled for c in changes] == [False, True, False, False]
    assert "Not a heading" in changes[2].body
    assert changes[1].title == "Remove default color prop"


def test_changes_for_symbol_uses_change_headings_only(spec: MigrationSpec) -> None:
    changes = parse_guide_file("x.md", GUIDE, spec.guide)
    assert [c.title for c in changes_for_symbol("Button", changes)] == [
        "Remove default color prop",
        "Remove span and label",
    ]
    assert changes_for_symbol("makeStyles", changes) == []


def test_vendored_guide_has_the_documented_marker_counts(spec: MigrationSpec) -> None:
    changes = load_guide(spec.guide_dir(), spec.guide)
    handled = [c for c in changes if c.codemod_handled]
    by_file = {f: sum(1 for c in handled if c.file == f) for f in spec.guide.files}
    assert by_file["v5-component-changes.md"] == 48
    assert by_file["v5-style-changes.md"] == 22
    assert all(c.section != "Material UI v5 migration" for c in changes)
    fade = changes_for_symbol("fade", changes)
    assert [c.id for c in fade] == ["v5-style-changes#@mui-material-styles/rename-fade-to-alpha"]
