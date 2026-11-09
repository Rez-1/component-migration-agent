"""Real runs (ticket #9): a git worktree on migrate/mui-v5, one commit per stage.

Real git on a small repo in tmp_path; the toolchain and the model are the fakes from
``tests.fakes``, so no Node and no LLM. The user's working tree must never change, the
run files must never be committed, and no stage may be committed twice, whether the
run goes straight through or pauses at a hand-off and is resumed by a new process.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import AIMessage

from migrator.cost import Ledger
from migrator.migrations import MigrationSpec
from migrator.pipeline import PausedRun, RunError, RunOptions, RunResult, resume_run, start_run
from migrator.repair.records import ReviewAnswer
from migrator.review import ReviewPayload
from migrator.workspace import Worktree, add_worktree, commit_stage, dirty_paths
from tests.conftest import FakeRunner
from tests.fakes import FakeToolchain, ScriptedChatModel, factory_for, make_mini_repo
from tests.test_graph import CARD, DASH, GOOD, THEME, Recorder, configuration

BRANCH = "migrate/mui-v5"


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout


def make_git_repo(root: Path, gitignore: bool = True) -> Path:
    repo = make_mini_repo(root)
    if gitignore:
        (repo / ".gitignore").write_text("node_modules/\n")
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.name", "Test User")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "commit.gpgsign", "false")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "A Material UI v4 app")
    return repo


@pytest.fixture(autouse=True)
def cache_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Worktrees go in the Migrator's cache folder; keep it inside tmp_path."""
    cache = tmp_path / "cache"
    monkeypatch.setenv("MIGRATOR_CACHE_DIR", str(cache))
    return cache


def real_run(
    tmp_path: Path,
    spec: MigrationSpec,
    *,
    reviewer: Any = None,
    script: dict[str, list[AIMessage]] | None = None,
    runner: FakeRunner | None = None,
) -> tuple[RunResult | PausedRun, Path, FakeRunner]:
    repo = tmp_path / "repo"
    if not repo.exists():
        make_git_repo(repo)
    runner = runner or FakeRunner(FakeToolchain())
    result = start_run(
        RunOptions.model_validate(
            {
                "repo": repo,
                "spec": spec,
                "run_dir": repo / ".migrator" / "runs" / "r1",
                "configuration": configuration(),
                "tools_cache": tmp_path / "tools",
                "run_id": "r1",
                "mode": "cli",
                "real": True,
            }
        ),
        runner,
        model_factory=factory_for(ScriptedChatModel(script=script or GOOD)),
        reviewer=reviewer or Recorder(["revert"]),
        ledger=Ledger(tmp_path / "ledger.jsonl"),
    )
    return result, repo, runner


def branch_commits(repo: Path) -> list[tuple[str, str]]:
    """(subject, Migrator-Stage) for each commit on the branch after main."""
    log = git(repo, "log", "--reverse", "--format=%s%x1f%B%x1e", f"main..{BRANCH}")
    out = []
    for entry in log.split("\x1e"):
        if not entry.strip():
            continue
        subject, body = entry.strip("\n").split("\x1f")
        stage = next(
            line.split(": ", 1)[1]
            for line in body.splitlines()
            if line.startswith("Migrator-Stage")
        )
        out.append((subject, stage))
    return out


def tree_files(repo: Path, ref: str) -> list[str]:
    return git(repo, "ls-tree", "-r", "--name-only", ref).split()


def test_a_real_run_commits_rules_and_agent_on_its_branch(
    tmp_path: Path, spec: MigrationSpec
) -> None:
    repo = make_git_repo(tmp_path / "repo")
    head = git(repo, "rev-parse", "HEAD")
    before = {p: (repo / p).read_bytes() for p in tree_files(repo, "HEAD")}

    result, _, _ = real_run(tmp_path, spec)
    assert isinstance(result, RunResult)
    assert result.branch == BRANCH

    # Rules, then the repair agent; ProfileCard's hand-off was reverted, so no Review commit.
    assert branch_commits(repo) == [
        ("Migrate mui@4 to mui@5: Rules (codemods and dependency map)", "rules"),
        ("Migrate mui@4 to mui@5: repair agent fixes in 2 files", "agent"),
    ]
    rules_files = git(repo, "show", "--name-only", "--format=", f"{BRANCH}~1").split()
    assert "package.json" in rules_files and THEME in rules_files
    agent_files = git(repo, "show", "--name-only", "--format=", BRANCH).split()
    assert sorted(agent_files) == [DASH, THEME]
    agent_msg = git(repo, "log", "-1", "--format=%B", BRANCH)
    assert "Handed off to Review (not in this commit):" in agent_msg
    assert f"- {CARD}:" in agent_msg
    assert "Migrator-Run: r1" in agent_msg

    # The migration branch holds the migrated code and nothing else.
    on_branch = tree_files(repo, BRANCH)
    assert not any(p.startswith((".migrator", "node_modules")) for p in on_branch)
    assert "@mui/material" in git(repo, "show", f"{BRANCH}:{THEME}")

    # The user's working tree and branch are untouched; the run files are beside it.
    assert git(repo, "rev-parse", "HEAD") == head
    assert git(repo, "symbolic-ref", "--short", "HEAD").strip() == "main"
    assert {p: (repo / p).read_bytes() for p in before} == before
    assert dirty_paths(repo) == []
    run_dir = repo / ".migrator" / "runs" / "r1"
    assert (run_dir / "scorecard.json").is_file() and (run_dir / "pr-body.md").is_file()

    # The worktree is removed at the end; the branch stays.
    assert git(repo, "worktree", "list").count("\n") == 1
    card = result.scorecard
    assert card.meta.branch == BRANCH and card.meta.base_branch == "main"
    assert [c.stage for c in card.meta.commits] == ["rules", "agent"]
    body = (run_dir / "pr-body.md").read_text()
    assert "## Commits" in body and "| Repair agent |" in body


def test_an_edit_at_review_is_its_own_commit(tmp_path: Path, spec: MigrationSpec) -> None:
    class Editor(Recorder):
        def review(self, payload: ReviewPayload) -> ReviewAnswer | None:
            utils = Path(payload.workspace) / "src/test-utils.tsx"
            utils.write_text(
                "import { ThemeProvider } from '@mui/material/styles';\n" + utils.read_text()
            )
            return ReviewAnswer(choice="edit")

    result, repo, _ = real_run(tmp_path, spec, reviewer=Editor([]))
    assert isinstance(result, RunResult)
    assert [stage for _, stage in branch_commits(repo)] == ["rules", "agent", "review"]
    review_files = git(repo, "show", "--name-only", "--format=", BRANCH).split()
    assert review_files == ["src/test-utils.tsx"]
    message = git(repo, "log", "-1", "--format=%B", BRANCH)
    assert f"- {CARD}: edited by a human; passes the narrow verify" in message
    assert "Also changed by the human: src/test-utils.tsx" in message


def test_pause_and_resume_never_commits_a_stage_twice(tmp_path: Path, spec: MigrationSpec) -> None:
    paused, repo, runner = real_run(tmp_path, spec, reviewer=Recorder([None]))
    assert isinstance(paused, PausedRun)
    # Paused at the hand-off: Rules and the agent are committed, the worktree is kept.
    assert [stage for _, stage in branch_commits(repo)] == ["rules", "agent"]
    worktree = Path(paused.payload.workspace)
    assert worktree.is_dir() and not worktree.is_relative_to(repo)

    # The human keeps the agent's (empty) patch and edits test-utils while paused.
    utils = worktree / "src/test-utils.tsx"
    utils.write_text("import { ThemeProvider } from '@mui/material/styles';\n" + utils.read_text())
    done = resume_run(
        repo / ".migrator" / "runs" / "r1",
        reviewer=Recorder(["keep"]),
        runner=runner,
        accept_changes=True,
        ledger=Ledger(tmp_path / "ledger.jsonl"),
    )
    assert isinstance(done, RunResult)
    assert [stage for _, stage in branch_commits(repo)] == ["rules", "agent", "review"]
    assert [c.stage for c in done.scorecard.meta.commits] == ["rules", "agent", "review"]
    assert not worktree.exists()


@pytest.mark.parametrize("gitignore", [True, False])
def test_a_stage_commit_is_made_once(tmp_path: Path, gitignore: bool) -> None:
    repo = make_git_repo(tmp_path / "repo", gitignore=gitignore)
    wt: Worktree = add_worktree(repo, tmp_path / "wt", BRANCH)
    (wt.path / "src/theme.ts").write_text("// migrated\n")
    (wt.path / "node_modules").mkdir()
    (wt.path / "node_modules/x.js").write_text("installed\n")
    (wt.path / "src/node_modules").mkdir()
    (wt.path / "src/node_modules/y.js").write_text("nested\n")
    (wt.path / ".migrator").mkdir()
    (wt.path / ".migrator/run.json").write_text("{}\n")
    first = commit_stage(wt, run_id="r9", stage="rules", title="Rules", body="b")
    assert first is not None and first.files == ["src/theme.ts"]  # never node_modules
    # A crash after the commit and before the checkpoint: the node runs again.
    (wt.path / "src/App.tsx").write_text("// stray\n")
    again = commit_stage(wt, run_id="r9", stage="rules", title="Rules", body="b")
    assert again is not None and again.sha == first.sha
    assert git(wt.path, "rev-list", "--count", "main..HEAD").strip() == "1"
    # Nothing to commit: no commit at all.
    git(wt.path, "checkout", "--", "src/App.tsx")
    assert commit_stage(wt, run_id="r9", stage="agent", title="Agent", body="b") is None


def test_a_dirty_working_tree_is_refused(tmp_path: Path, spec: MigrationSpec) -> None:
    repo = make_git_repo(tmp_path / "repo")
    (repo / THEME).write_text("// work in progress\n")
    with pytest.raises(RunError, match=r"uncommitted changes \(src/theme.ts\)"):
        real_run(tmp_path, spec)
    git(repo, "checkout", "--", THEME)
    (repo / "notes.txt").write_text("untracked\n")
    with pytest.raises(RunError, match=r"notes\.txt"):
        real_run(tmp_path, spec)
    assert not (tmp_path / "cache" / "worktrees").exists()  # refused before any worktree


def test_the_run_files_folder_does_not_make_the_tree_dirty(tmp_path: Path) -> None:
    repo = make_git_repo(tmp_path / "repo")
    (repo / ".migrator" / "runs" / "old").mkdir(parents=True)
    (repo / ".migrator" / "runs" / "old" / "run.json").write_text("{}")
    assert dirty_paths(repo) == []


def test_an_existing_branch_is_refused(tmp_path: Path, spec: MigrationSpec) -> None:
    repo = make_git_repo(tmp_path / "repo")
    git(repo, "branch", BRANCH)
    with pytest.raises(RunError, match="already exists"):
        real_run(tmp_path, spec)


def test_a_real_run_needs_a_git_repo(tmp_path: Path, spec: MigrationSpec) -> None:
    make_mini_repo(tmp_path / "repo")
    with pytest.raises(RunError, match="not a git repository"):
        real_run(tmp_path, spec)


def test_an_eval_never_makes_a_real_run(tmp_path: Path, spec: MigrationSpec) -> None:
    repo = make_git_repo(tmp_path / "repo")
    with pytest.raises(RunError, match="evals only make dry runs"):
        start_run(
            RunOptions(repo=repo, spec=spec, run_dir=tmp_path / "run", real=True, mode="eval"),
            FakeRunner(FakeToolchain()),
        )
