"""Opening a pull request for a real run's branch: a separate, flagged step.

``migrator pr <run> [--open]`` (the brief: PRs only to your own repos or forks, never
upstream and never during evals, as a separate flagged step):

- **Without ``--open``** it only prints what it would do: the push and the
  ``gh pr create`` command, the title and the body file. Nothing runs, nothing leaves
  the machine.
- **With ``--open``** it checks, then pushes the branch and opens the PR with ``gh``.

The rule, checked before anything is pushed:

1. The run is a finished real run (it has a branch and stage commits). Dry runs, eval
   runs and runs still paused at Review are refused, and so is a run whose PR is open.
2. The remote (``origin`` unless ``--remote``) is a GitHub repository, and its owner is
   the account ``gh`` is logged in as (``gh api user``). Your own repos and your forks
   pass; an organisation's repo or anyone else's is refused.
3. The PR is created with an explicit ``--repo <owner>/<name> --head <branch> --base
   <base>``: in a fork, ``gh pr create`` would otherwise target the upstream repo.

Every external command goes through a ``CommandRunner`` (``LocalRunner`` in the CLI), so
the tests run it against a stub ``gh`` and a local bare repo.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

from pydantic import BaseModel

from migrator.execs import CommandRunner
from migrator.pipeline import RunError, read_run_record, write_run_record
from migrator.report import pr_title
from migrator.scoring import Scorecard

_GITHUB_URL = re.compile(
    r"^(?:https://(?:[^@/]+@)?github\.com/|ssh://git@github\.com/|git@github\.com:)"
    r"(?P<owner>[A-Za-z0-9-]+)/(?P<name>[A-Za-z0-9._-]+?)(?:\.git)?/?$"
)


class PrError(RunError):
    """The PR step refused, or a command it ran failed."""


class GitHubRepo(BaseModel):
    owner: str
    name: str

    @property
    def slug(self) -> str:
        return f"{self.owner}/{self.name}"


def parse_github_url(url: str) -> GitHubRepo | None:
    m = _GITHUB_URL.match(url.strip())
    return GitHubRepo(owner=m["owner"], name=m["name"]) if m else None


class PrPlan(BaseModel):
    """What ``migrator pr`` would do for a run."""

    run_id: str
    run_dir: Path
    repo_dir: Path
    branch: str
    base: str
    remote: str
    github: GitHubRepo
    title: str
    body_file: Path
    draft: bool

    def push_command(self) -> list[str]:
        return ["git", "push", self.remote, f"refs/heads/{self.branch}:refs/heads/{self.branch}"]

    def create_command(self, gh: str = "gh") -> list[str]:
        command = [
            gh, "pr", "create",
            "--repo", self.github.slug,
            "--head", self.branch,
            "--base", self.base,
            "--title", self.title,
            "--body-file", str(self.body_file.resolve()),
        ]  # fmt: skip
        return [*command, "--draft"] if self.draft else command

    def describe(self) -> list[str]:
        return [
            f"Would check that `gh api user` is {self.github.owner} (the owner of "
            f"{self.github.slug}, the {self.remote} remote), then:",
            f"  $ {shlex.join(self.push_command())}   (in {self.repo_dir})",
            f"  $ {shlex.join(self.create_command())}",
            f"Title: {self.title}",
            f"Body: {self.body_file}",
        ]


def _run(runner: CommandRunner, argv: list[str], cwd: Path, what: str) -> str:
    result = runner.run(argv, cwd, timeout_s=300)
    if not result.ok:
        raise PrError(f"{what} failed (`{shlex.join(argv)}` exited {result.exit_code}): "
                      f"{result.output.strip()[-500:]}")  # fmt: skip
    return result.output.strip()


def plan_pr(
    run_dir: Path,
    runner: CommandRunner,
    *,
    remote: str = "origin",
    base: str | None = None,
    draft: bool = False,
) -> PrPlan:
    """Check the run (rule 1) and read the remote; nothing leaves the machine."""
    record = read_run_record(run_dir)
    if record.mode == "eval":
        raise PrError("this run is part of an eval; evals never open pull requests")
    if record.worktree is None:
        raise PrError(
            f"run {record.run_id} is a dry run: it has no branch to open a PR for "
            "(run `migrator migrate` without --dry-run)"
        )
    if record.status != "done":
        raise PrError(
            f"run {record.run_id} is {record.status}; finish it first (`migrator resume {run_dir}`)"
        )
    if record.pr_url:
        raise PrError(f"run {record.run_id} already has a pull request: {record.pr_url}")
    card = Scorecard.model_validate_json((run_dir / "scorecard.json").read_text("utf-8"))
    if not card.meta.commits:
        raise PrError(f"run {record.run_id} made no commits, so there is nothing to propose")
    body = run_dir / "pr-body.md"
    if not body.is_file():
        raise PrError(f"{body} is missing")
    wt = record.worktree
    target = base or wt.base_branch
    if not target:
        raise PrError("the run started on a detached HEAD; pass --base <branch>")
    url = _run(runner, ["git", "remote", "get-url", remote], wt.repo, f"reading the {remote} URL")
    github = parse_github_url(url)
    if github is None:
        raise PrError(
            f"the {remote} remote ({url}) is not a GitHub repository; the Migrator opens "
            "pull requests on GitHub only"
        )
    return PrPlan(
        run_id=record.run_id,
        run_dir=run_dir,
        repo_dir=wt.repo,
        branch=wt.branch,
        base=target,
        remote=remote,
        github=github,
        title=pr_title(card),
        body_file=body,
        draft=draft,
    )


def open_pr(plan: PrPlan, runner: CommandRunner, *, gh: str = "gh") -> str:
    """Check the owner (rule 2), push the branch and open the PR (rule 3); its URL."""
    login = _run(runner, [gh, "api", "user", "--jq", ".login"], plan.repo_dir, "`gh api user`")
    if login.lower() != plan.github.owner.lower():
        raise PrError(
            f"{plan.github.slug} belongs to {plan.github.owner}, but gh is logged in as "
            f"{login}: the Migrator opens pull requests only on your own repositories and "
            "forks. Push the branch yourself if this is intended."
        )
    _run(runner, plan.push_command(), plan.repo_dir, "pushing the branch")
    output = _run(runner, plan.create_command(gh), plan.repo_dir, "`gh pr create`")
    url = next(
        (w for w in reversed(output.split()) if w.startswith("https://")), output.splitlines()[-1]
    )
    record = read_run_record(plan.run_dir)
    write_run_record(plan.run_dir, record.model_copy(update={"pr_url": url}))
    return url
