from __future__ import annotations

from pathlib import Path

from migrator.workspace import (
    changed_files,
    create_dry_run_workspace,
    install_command,
    installed_manifest,
    list_files,
    manifest_hash,
    matches,
    record_install,
    snapshot,
)


def _tree(root: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)


def test_list_files_matches_globs_and_excludes(tmp_path: Path) -> None:
    _tree(
        tmp_path,
        {
            "src/a.tsx": "",
            "src/deep/b.ts": "",
            "src/c.css": "",
            "src/gen/d.ts": "",
            "node_modules/x/index.ts": "",
        },
    )
    found = list_files(tmp_path, ["src/**/*.ts", "src/**/*.tsx", "**/*.ts"], ["src/gen/**"])
    assert found == ["src/a.tsx", "src/deep/b.ts"]


def test_matches_double_star() -> None:
    assert matches("a/node_modules/b/c.js", ["**/node_modules/**"])
    assert matches("src/x.tsx", ["src/**/*.tsx"])
    assert not matches("lib/x.tsx", ["src/**/*.tsx"])


def test_snapshot_detects_changed_added_and_removed(tmp_path: Path) -> None:
    _tree(tmp_path, {"a.ts": "1", "b.ts": "2"})
    before = snapshot(tmp_path, ["a.ts", "b.ts", "c.ts"])
    (tmp_path / "a.ts").write_text("1")  # same content: not a change
    (tmp_path / "b.ts").write_text("changed")
    (tmp_path / "c.ts").write_text("new")
    after = snapshot(tmp_path, ["a.ts", "b.ts", "c.ts"])
    assert changed_files(before, after) == ["b.ts", "c.ts"]
    (tmp_path / "c.ts").unlink()
    assert changed_files(after, snapshot(tmp_path, ["a.ts", "b.ts", "c.ts"])) == ["c.ts"]


def test_dry_run_workspace_leaves_out_git_and_node_modules(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _tree(
        repo, {"src/a.ts": "x", ".git/HEAD": "ref", "node_modules/p/i.js": "", "package.json": "{}"}
    )
    ws = create_dry_run_workspace(repo, tmp_path / "ws")
    assert (ws / "src/a.ts").read_text() == "x"
    assert not (ws / ".git").exists()
    assert not (ws / "node_modules").exists()
    (ws / "src/a.ts").write_text("changed")
    assert (repo / "src/a.ts").read_text() == "x"


def test_install_commands() -> None:
    assert install_command("npm", True) == ["npm", "ci", "--no-audit", "--no-fund"]
    assert install_command("npm", False, ["--legacy-peer-deps"])[-1] == "--legacy-peer-deps"
    assert install_command("pnpm", True) == ["pnpm", "install", "--frozen-lockfile"]


def test_install_marker_tracks_the_manifest(tmp_path: Path) -> None:
    _tree(tmp_path, {"package.json": "{}", "package-lock.json": "{}", "node_modules/.keep": ""})
    assert installed_manifest(tmp_path) is None
    record_install(tmp_path, "package-lock.json")
    assert installed_manifest(tmp_path) == manifest_hash(tmp_path, "package-lock.json")
    (tmp_path / "package.json").write_text('{"dependencies": {}}')
    assert installed_manifest(tmp_path) != manifest_hash(tmp_path, "package-lock.json")
