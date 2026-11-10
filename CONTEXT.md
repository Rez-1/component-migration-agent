# Component Migration

The Migrator moves a target repo from one component-library version to another (first `mui@4 → mui@5`): rules first, the repair agent second, gated by verification and measured by evals.

## Language

### The tool and its work

**Migrator**:
The whole tool: it takes a target repo through every stage of a run.
_Avoid_: agent (for the whole tool), bot

**Repair agent**:
The LLM loop inside the Migrator that fixes failing files.
_Avoid_: agent (unqualified), LLM (as a name for this part)

**Migration**:
One supported version jump of a component library, such as `mui@4 → mui@5`.
_Avoid_: upgrade, recipe

**Migration spec**:
The description of one migration that the Migrator reads: what changes and how the rules stage handles it.
_Avoid_: recipe, config

**Target repo**:
The codebase a run migrates.
_Avoid_: project, app, codebase

**Run**:
One execution of the Migrator on one target repo, from the CLI or from an eval.
_Avoid_: execution, job, trial

**Workspace**:
The copy of the target repo that a run changes; the original is untouched until changes land on its branch.
_Avoid_: sandbox, copy, temp dir

### Stages and layers

**Stage**:
One step of a run, in order: Scan, Pre-check, Rules, Verify, Repair, Review, Report. Verify runs again after Review as the final check.
_Avoid_: phase, step, pass

**Pre-check**:
The verification of the untouched workspace before any change.
_Avoid_: baseline verify, initial check

**Pre-existing failure**:
A failure the pre-check finds, so it is not charged to the run.
_Avoid_: known failure, baseline failure

**Layer**:
Who last changed a file: Rules, Agent or Human.
_Avoid_: LLM (as a layer), source, owner (except a trap's expected owner)

**Rules**:
The deterministic layer: the dependency map, the official codemods and any of our own rules.
_Avoid_: codemod layer, rules pass

**Rule step**:
One entry in a migration spec's ordered list for the Rules stage: install, dependencies, codemod, format or script.
_Avoid_: step (unqualified), action, task

**Rules failure**:
A run that stopped because a rule step failed, scored separately from the repair agent's results.
_Avoid_: setup failure, install error

**Baseline**:
The rules-only configuration that every other configuration is compared against.
_Avoid_: control, codemod only

### Verification and repair

**Failure**:
One problem reported by verification (a type error, a lint error or a failing test), with its file, line and message.
_Avoid_: error, issue, problem (as the general term)

**Failing file**:
A file with at least one failure.

**Regression**:
A failure in a file that had none before, caused by a change to another file during the run.
_Avoid_: side effect, collateral failure

**Attempt**:
One try by the repair agent to fix one failing file.
_Avoid_: iteration, retry (as a noun)

**Edit**:
One find-and-replace change the repair agent makes to a file.
_Avoid_: change, diff (for a single edit)

**Patch**:
All of the repair agent's edits to one file in a run, across every attempt; the size limit for a hand-off applies to it.
_Avoid_: fix, change set

**Hand-off**:
One file passed to a human, because the repair agent gave up or its patch was over the size limit.
_Avoid_: escalation, TODO, manual fix

**Review list**:
The hand-offs of one run.

**Guardrail**:
A block the repair agent's tools enforce, such as refusing writes to test files.
_Avoid_: cheating check, restriction

**Cheating check**:
A rule run on a run's final diff to catch gamed success, such as an added `.skip`.
_Avoid_: guardrail, lint

**Escape hatch**:
Code that silences a type or lint check instead of satisfying it, such as `@ts-ignore`, `eslint-disable` or an `any` type.
_Avoid_: suppression, workaround

**Test file**:
A file that belongs to the tests rather than the code under test: matched by the runner's test globs, named as a setup file in its config, inside `__mocks__` or `__snapshots__`, or imported only by other test files.
_Avoid_: spec (for a file)

**Codemod TODO**:
A FIXME or TODO comment the official codemods leave in a file, marking work they could not do.
_Avoid_: codemod warning

**Codemod false positive**:
A codemod change to a component that comes from the repo's own code rather than from the library being migrated (the codemods match by name), which the Rules stage undoes and lists for a human. On OpossumUI: `size="large"` added to the repo's own `IconButton` wrapper.
_Avoid_: codemod bug, wrong codemod change

### Evals

**Case**:
One eval input: a target-repo snapshot, its verify commands and optionally a reference.
_Avoid_: example, sample, task, benchmark item

**Fixture**:
The purpose-built target repo written against the old library version, with planted traps.
_Avoid_: demo app, test app

**Fixture case**:
A case whose target repo is the fixture.

**Breaking change**:
A change in the library between versions, as its migration guide describes it.
_Avoid_: trap (for the library change itself)

**Trap**:
One planted instance of a breaking change in the fixture, with the layer expected to handle it.
_Avoid_: gotcha, pitfall

**Trap result**:
How a run handled one trap: Expected (the expected layer handled it; for a human trap, it was handed off), Other layer, or Missed.

**Silent miss**:
A Missed agent or human trap whose checks all pass at the final verify, so verify can't show it. Either the breaking change is still in the code with no check covering it, or it was fixed in a different file than the trap's. Only a human reading the diff can tell which; counted on its own in every scorecard and experiment summary. On a real repo, scored against its migration PR: a scoring item judged *wrong* or *untouched* whose file has no failure at the final verify and was not handed off.

**Configuration**:
Everything an experiment varies: model per attempt, effort, repair prompt, retrieval mode, max attempts, cost caps and which rules are on. The baseline is the configuration with repair turned off.
_Avoid_: variant, arm, settings

**Split**:
Either the dev set (climbed on) or the held-out set (run only at milestones).

**Experiment**:
All runs of one configuration over a split.
_Avoid_: trial, sweep

**Reference**:
The diff of the real migration PR for a case.
_Avoid_: answer key, ground truth, golden

### Reports

**Usage**:
One reference to the old library in a file: an import, a JSX element or a call.
_Avoid_: occurrence, hit

**Affected file**:
A file with at least one usage before the run.

**Outcome**:
How one affected file ends a run: Migrated by rules, Migrated by agent, Migrated by human, Handed off, or Unmigrated.
_Avoid_: status, result (for a file)

**Clean run**:
A run whose final verify finds no failures outside handed-off files.
_Avoid_: passing run, green run, verify pass

**Scorecard**:
The measured results of one run, including the count of each outcome.
_Avoid_: report card, results

**Experiment summary**:
The aggregate of an experiment's scorecards, with mean and spread.
_Avoid_: leaderboard
