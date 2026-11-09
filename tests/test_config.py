from __future__ import annotations

import json
from pathlib import Path

import pytest

from migrator.config import (
    ConfigError,
    RepoConfig,
    VerifyCommands,
    detect_package_manager,
    detect_verify_commands,
    load_case,
    load_traps,
    resolve_repo_config,
)
from tests.conftest import FIXTURE_CASE


def _repo(tmp_path: Path, scripts: dict[str, str], lockfile: str = "package-lock.json") -> Path:
    (tmp_path / "package.json").write_text(
        json.dumps({"name": "x", "scripts": scripts, "devDependencies": {"jest": "29"}})
    )
    if lockfile:
        (tmp_path / lockfile).write_text("")
    return tmp_path


@pytest.mark.parametrize(
    ("lockfile", "manager"),
    [("package-lock.json", "npm"), ("yarn.lock", "yarn"), ("pnpm-lock.yaml", "pnpm")],
)
def test_package_manager_from_lockfile(tmp_path: Path, lockfile: str, manager: str) -> None:
    (tmp_path / lockfile).write_text("")
    assert detect_package_manager(tmp_path) == (manager, lockfile)


def test_a_repo_without_lockfile_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="no lockfile"):
        detect_package_manager(tmp_path)


def test_verify_commands_detected_from_scripts(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {"type-check": "tsc", "lint": "eslint .", "test": "jest"}, "yarn.lock")
    assert detect_verify_commands(repo, "yarn") == VerifyCommands(
        typecheck="yarn type-check", lint="yarn lint", test="yarn test"
    )


def test_case_overrides_migrate_toml_per_field(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {"lint": "eslint .", "test": "jest"})
    (repo / "migrate.toml").write_text(
        'install_flags = ["--legacy-peer-deps"]\nsource_globs = ["app/**/*.tsx"]\n'
        '[verify]\ntest = "npm run test:ci"\n'
    )
    override = RepoConfig(source_globs=["src/**/*.ts"], verify=VerifyCommands(lint="npm run l"))
    resolved = resolve_repo_config(repo, override, ["default/**"], [])
    assert resolved.source_globs == ["src/**/*.ts"]
    assert resolved.install_flags == ["--legacy-peer-deps"]
    assert resolved.verify.test == "npm run test:ci"
    assert resolved.verify.lint == "npm run l"
    assert resolved.verify.typecheck is None
    assert resolved.runner == "jest"


def test_fixture_case_loads() -> None:
    case = load_case(FIXTURE_CASE / "case.toml")
    assert case.id == "fixture-mui4"
    assert case.runner == "jest"
    assert case.repo.verify == VerifyCommands(
        typecheck="npm run typecheck", lint="npm run lint", test="npm test"
    )
    assert case.traps_path() == FIXTURE_CASE / "traps.yaml"


def test_fixture_traps_load() -> None:
    traps = load_traps(FIXTURE_CASE / "traps.yaml")
    layers = [t.expected_layer for t in traps.traps]
    assert len(traps.traps) == 23  # fixture revision 2
    assert layers.count("rules") == 12
    assert layers.count("agent") == 9
    assert layers.count("human") == 1
    assert layers.count("visual-only") == 1
    search = next(t for t in traps.traps if t.id == "autocomplete-render-option")
    assert search.checks()[0] == "typecheck"
