"""`migrator init`: detectors and the written migrate.toml (M6)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from migrator.config import load_repo_config
from migrator.init import InitError, detect, render_migrate_toml, write_migrate_toml


def _repo(tmp_path: Path, package: dict[str, object], files: dict[str, str]) -> Path:
    (tmp_path / "package.json").write_text(json.dumps(package))
    for name, text in files.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(text)
    return tmp_path


def test_a_cra_yarn_repo_like_opossum(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        {
            "scripts": {
                "compile-all": "tsc -p ./",
                "lint": "eslint src --fix",
                "lint-check": "eslint src",
                "test:unit": "react-scripts test --watchAll=false",
            },
            "devDependencies": {"react-scripts": "4.0.3", "electron": "13", "playwright": "1"},
        },
        {"yarn.lock": "", "src/App.tsx": "", "src/util.ts": ""},
    )
    r = detect(repo)
    assert r.package_manager.value == "yarn" and r.runner.value == "jest"
    assert r.typecheck.value == "yarn compile-all"
    assert r.lint.value == "yarn lint-check"  # never the --fix script
    assert r.test.value == "yarn test:unit"
    assert r.install_env.value == {
        "ELECTRON_SKIP_BINARY_DOWNLOAD": "1",
        "PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD": "1",
    }
    assert r.source_globs.value == ["src/**/*.ts", "src/**/*.tsx"]
    assert [t.split(":")[0] for t in r.todos] == ["Node version"]


def test_a_vitest_npm_repo_like_kubeflow(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        {
            "scripts": {"typecheck": "tsc --noEmit", "lint": "eslint src", "test": "vitest run"},
            "devDependencies": {"vitest": "^4.0.17"},
        },
        {"package-lock.json": "{}", ".nvmrc": "v22.19.0\n", "src/a.tsx": ""},
    )
    r = detect(repo)
    assert (r.node.value, r.runner.value) == ("22", "vitest")
    assert (r.typecheck.value, r.lint.value, r.test.value) == (
        "npm run typecheck",
        "npm run lint",
        "npm test",
    )
    assert r.todos == []


def test_cra_test_gets_watch_off_and_an_unpinned_node_is_a_todo(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        {
            "engines": {"node": "~14.x"},
            "scripts": {"test": "react-scripts test", "lint": "eslint --fix src"},
            "dependencies": {"react-scripts": "5"},
        },
        {"package-lock.json": "{}", "tsconfig.json": "{}", "src/a.ts": ""},
    )
    r = detect(repo)
    assert r.test.value == "npm test -- --watchAll=false"
    assert r.typecheck.value == "npx tsc --noEmit"
    assert r.lint.value is None and "--fix" in r.lint.source
    assert r.node.value is None and "Node 14" in r.node.source
    assert {t.split(":")[0] for t in r.todos} == {"Node version", "lint command"}


def test_the_written_file_loads_and_is_never_overwritten(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        {"scripts": {"test": "jest"}, "devDependencies": {"jest": "29"}},
        {"package-lock.json": "{}", ".node-version": "20\n", "src/a.ts": ""},
    )
    path, _ = write_migrate_toml(repo)
    config = load_repo_config(repo)
    assert (config.node, config.runner) == ("20", "jest")
    assert config.verify is not None and config.verify.test == "npm test"
    with pytest.raises(InitError, match="--force"):
        write_migrate_toml(repo)
    write_migrate_toml(repo, force=True)
    assert "# from scripts.test" in path.read_text()
    assert render_migrate_toml(detect(repo)) == path.read_text()
