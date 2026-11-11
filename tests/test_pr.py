"""``migrator pr``: a separate, flagged step, against a stub ``gh`` and a local bare repo.

The remote's fetch URL is a GitHub URL (what the owner check reads); its push URL is a
bare repo in tmp_path, so a push never leaves the machine. The stub ``gh`` logs its
arguments and answers ``api user`` and ``pr create``. No test contacts GitHub.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest
from typer.testing import CliRunner

from migrator.cli import app
from migrator.migrations import MigrationSpec
from migrator.pipeline import RunResult
from migrator.pr import parse_github_url
from tests.test_real_run import BRANCH, cache_dir, git, real_run

cli = CliRunner()
__all__ = ["cache_dir"]  # the autouse fixture: worktrees go in tmp_path, not ~/.cache

GH_STUB = """#!/bin/sh
echo "$@" >> "$GH_LOG"
if [ "$1 $2" = "api user" ]; then echo "$GH_LOGIN"; exit 0; fi
if [ "$1 $2" = "pr create" ]; then echo "https://github.com/rez/mini-app/pull/7"; exit 0; fi
echo "unexpected gh call" >&2; exit 1
"""


@pytest.fixture
def gh(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "gh"
    stub.write_text(GH_STUB)
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    log = tmp_path / "gh.log"
    log.touch()
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("GH_LOG", str(log))
    monkeypatch.setenv("GH_LOGIN", "rez")
    return log


def finished_run(tmp_path: Path, spec: MigrationSpec, url: str) -> tuple[Path, Path, Path]:
    """A finished real run whose repo has an origin: (repo, run folder, bare repo)."""
    result, repo, _ = real_run(tmp_path, spec)
    assert isinstance(result, RunResult)
    bare = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", str(bare))
    git(repo, "remote", "add", "origin", url)
    git(repo, "remote", "set-url", "--push", "origin", str(bare))
    return repo, result.run_dir, bare


def remote_branches(bare: Path) -> list[str]:
    return git(bare, "for-each-ref", "--format=%(refname:short)", "refs/heads").split()


def test_github_remote_urls() -> None:
    for url in (
        "https://github.com/rez/mini-app.git",
        "https://github.com/rez/mini-app",
        "git@github.com:rez/mini-app.git",
        "ssh://git@github.com/rez/mini-app.git",
    ):
        parsed = parse_github_url(url)
        assert parsed is not None and parsed.slug == "rez/mini-app", url
    assert parse_github_url("https://gitlab.com/rez/mini-app.git") is None
    assert parse_github_url("/tmp/remote.git") is None


def test_without_open_it_only_shows_what_it_would_do(
    tmp_path: Path, spec: MigrationSpec, gh: Path
) -> None:
    _, run_dir, bare = finished_run(tmp_path, spec, "https://github.com/rez/mini-app.git")
    result = cli.invoke(app, ["pr", str(run_dir)])
    assert result.exit_code == 0, result.output
    out = " ".join(result.output.split())
    assert "Would check that `gh api user` is rez" in out
    assert f"git push origin refs/heads/{BRANCH}:refs/heads/{BRANCH}" in out
    assert "gh pr create --repo rez/mini-app --head migrate/mui-v5 --base main" in out
    assert "Nothing was pushed" in out
    assert gh.read_text() == ""  # gh never ran
    assert remote_branches(bare) == []


def test_open_pushes_the_branch_and_opens_the_pr_on_the_users_repo(
    tmp_path: Path, spec: MigrationSpec, gh: Path
) -> None:
    repo, run_dir, bare = finished_run(tmp_path, spec, "git@github.com:rez/mini-app.git")
    result = cli.invoke(app, ["pr", str(run_dir), "--open", "--draft"])
    assert result.exit_code == 0, result.output
    assert "Opened https://github.com/rez/mini-app/pull/7" in result.output
    assert remote_branches(bare) == [BRANCH]
    assert git(bare, "rev-parse", BRANCH) == git(repo, "rev-parse", BRANCH)
    calls = gh.read_text().splitlines()
    assert calls[0] == "api user --jq .login"
    assert calls[1].startswith(
        "pr create --repo rez/mini-app --head migrate/mui-v5 --base main --title Migrate mui@4"
    )
    assert f"--body-file {run_dir / 'pr-body.md'}" in calls[1] and calls[1].endswith("--draft")
    record = json.loads((run_dir / "run.json").read_text())
    assert record["pr_url"] == "https://github.com/rez/mini-app/pull/7"
    again = cli.invoke(app, ["pr", str(run_dir), "--open"])
    assert again.exit_code == 2 and "already has a pull request" in again.output


def test_a_repo_the_user_does_not_own_is_refused_before_any_push(
    tmp_path: Path, spec: MigrationSpec, gh: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, run_dir, bare = finished_run(tmp_path, spec, "https://github.com/mui/material-ui.git")
    result = cli.invoke(app, ["pr", str(run_dir), "--open"])
    assert result.exit_code == 2
    assert "only on your own repositories and forks" in " ".join(result.output.split())
    assert gh.read_text().splitlines() == ["api user --jq .login"]
    assert remote_branches(bare) == []


def test_a_non_github_remote_is_refused(tmp_path: Path, spec: MigrationSpec, gh: Path) -> None:
    _, run_dir, _ = finished_run(tmp_path, spec, "https://gitlab.com/rez/mini-app.git")
    result = cli.invoke(app, ["pr", str(run_dir), "--open"])
    assert result.exit_code == 2 and "GitHub only" in " ".join(result.output.split())
    assert gh.read_text() == ""


def test_dry_runs_and_eval_runs_never_open_a_pr(
    tmp_path: Path, spec: MigrationSpec, gh: Path
) -> None:
    _, run_dir, _ = finished_run(tmp_path, spec, "https://github.com/rez/mini-app.git")
    record = json.loads((run_dir / "run.json").read_text())
    (run_dir / "run.json").write_text(json.dumps({**record, "mode": "eval"}))
    result = cli.invoke(app, ["pr", str(run_dir), "--open"])
    assert result.exit_code == 2 and "evals never open pull requests" in result.output
    (run_dir / "run.json").write_text(json.dumps({**record, "worktree": None}))
    result = cli.invoke(app, ["pr", str(run_dir), "--open"])
    assert result.exit_code == 2 and "is a dry run" in result.output
    (run_dir / "run.json").write_text(json.dumps({**record, "status": "paused"}))
    result = cli.invoke(app, ["pr", str(run_dir), "--open"])
    assert result.exit_code == 2 and "is paused" in result.output
    assert gh.read_text() == ""


def test_the_body_file_is_passed_as_an_absolute_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """gh runs inside the migrated repo, so a run folder given relative to the Migrator's
    folder (``runs/...``) must not reach it as a relative path."""
    from migrator.pr import PrPlan

    monkeypatch.chdir(tmp_path)
    plan = PrPlan(
        run_id="r", run_dir=Path("runs/r"), repo_dir=tmp_path / "repo", branch="b",
        base="main", remote="origin", github=parse_github_url("https://github.com/rez/mini-app"),
        title="t", body_file=Path("runs/r/pr-body.md"), draft=False,
    )  # fmt: skip
    command = plan.create_command()
    body = command[command.index("--body-file") + 1]
    assert body == str(tmp_path.resolve() / "runs/r/pr-body.md")
