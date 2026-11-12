"""Scoring: the evidence of a finished workspace in, its Scorecard out (issue #17).

The same rules whatever changed the workspace. A pure, in-process package: it runs no
Verify, scan or Cheating check and reads no files. Callers import only from here:

- ``score(evidence)``: the Scorecard of one run, from the Migrator
  (``MigratorChanges``) or from a general coding agent (``AgentChanges``).
- ``run_metrics(card)`` and ``METRICS``: the one per-run metric list, which the
  experiment summary, ``grade()`` and the hill-climb keep rule all read.
- The Scorecard schema and ``stable_view``, its deterministic part.
"""

from migrator.scoring._score import score
from migrator.scoring.evidence import AgentChanges, Evidence, MigratorChanges, Unfinished
from migrator.scoring.metrics import METRICS, Metric, Unit, ViewerColumn, run_metrics
from migrator.scoring.scorecard import (
    OUTCOMES,
    SCHEMA_VERSION,
    AttemptSummary,
    CommandSummary,
    CoverageSummary,
    FileRepairSummary,
    FileResult,
    Headline,
    Outcome,
    PrecheckSummary,
    RegressionsAgainst,
    RepairSummary,
    RepeatedEdit,
    RulesSummary,
    RunMeta,
    RunStatus,
    Scorecard,
    Share,
    SnapshotUpdate,
    StepSummary,
    TestFittingFlag,
    TrapCheck,
    TrapCounts,
    TrapResult,
    TrapResultName,
    VerifySummary,
    stable_view,
)

__all__ = [
    "METRICS",
    "OUTCOMES",
    "SCHEMA_VERSION",
    "AgentChanges",
    "AttemptSummary",
    "CommandSummary",
    "CoverageSummary",
    "Evidence",
    "FileRepairSummary",
    "FileResult",
    "Headline",
    "Metric",
    "MigratorChanges",
    "Outcome",
    "PrecheckSummary",
    "RegressionsAgainst",
    "RepairSummary",
    "RepeatedEdit",
    "RulesSummary",
    "RunMeta",
    "RunStatus",
    "Scorecard",
    "Share",
    "SnapshotUpdate",
    "StepSummary",
    "TestFittingFlag",
    "TrapCheck",
    "TrapCounts",
    "TrapResult",
    "TrapResultName",
    "Unfinished",
    "Unit",
    "VerifySummary",
    "ViewerColumn",
    "run_metrics",
    "score",
    "stable_view",
]
