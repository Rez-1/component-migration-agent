"""The evidence Scoring reads: what every workspace has, and what changed it.

``Evidence`` holds the fields any finished workspace has (the Pre-check, the final
Verify, the usage before and after, the Cheating check report, the Traps, cost, meta,
the Configuration and the Case). ``changes`` says what changed the workspace: the
Migrator's stages (``MigratorChanges``).

The graph writes a run's evidence to ``report-input.json`` in its run folder before
Scoring runs, so the evidence survives a crash in Scoring and the run can be scored
again (``Evidence.model_validate_json``).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from migrator.checks import CheatingReport, Layer
from migrator.config import TrapList
from migrator.configuration import DEFAULT_MAX_MONTH_USD, DEFAULT_MAX_RUN_USD
from migrator.cost import RunCost
from migrator.repair.records import RepairReport
from migrator.rules import RulesResult
from migrator.scan import UsageReport
from migrator.scoring.scorecard import (
    RepeatedEdit,
    RunMeta,
    SnapshotUpdate,
    TestFittingFlag,
)
from migrator.verify import PrecheckResult, VerifyResult
from migrator.visual.compare import VisualReport


class MigratorChanges(BaseModel):
    """What the Migrator's stages did: Rules, Repair, Review, and the review aids."""

    kind: Literal["migrator"] = "migrator"
    # None: Rules never ran (the run stopped before it), which is still a Rules failure.
    rules: RulesResult | None
    # The Verify right after Rules; Regressions are counted against it. None means the
    # run changed nothing after Rules, so the final Verify is that Verify.
    rules_verify: VerifyResult | None = None
    repair: RepairReport | None = None  # None when repair is off (the Baseline)
    # Who changed each file after Rules ("agent" or "human"); None: nobody did.
    later_layers: dict[str, Layer] | None = None
    snapshots_to_review: list[SnapshotUpdate] | None = None
    visual: VisualReport | None = None
    repeated_edits: list[RepeatedEdit] | None = None
    test_fitting: list[TestFittingFlag] | None = None


class Evidence(BaseModel):
    """Everything Scoring reads about one finished workspace."""

    usage: UsageReport  # the scan before the run: its Affected files
    precheck: PrecheckResult
    verify: VerifyResult | None  # the final Verify; None when the run stopped before it
    final_usage: UsageReport | None  # the rescan after the run
    traps: TrapList | None
    configuration: str = "baseline"
    configuration_digest: str | None = None
    case: str | None = None
    cheating: CheatingReport | None = None
    cost: RunCost = RunCost.no_llm(DEFAULT_MAX_RUN_USD, DEFAULT_MAX_MONTH_USD)
    meta: RunMeta
    changes: MigratorChanges
