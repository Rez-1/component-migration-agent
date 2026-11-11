"""The test-fitting reviewer (M6, the owner's option D): a second model, on flagged
patches only.

The free test-fitting flag fires when a passing patch for a file that failed a test
changes accessibility props or the rendered element. That catches the agent fitting a
component to an outdated v4 test (OpossumUI: ``describeChild`` added, an ``aria-label``
removed), but also legitimate v5 changes (kubeflow: a ``<div>`` that v5's ``Slide``
needs around ``Resizable``, which the developers made too). So a flagged patch goes to
one call of a different model than the repair agent's (the balanced level: Claude
Sonnet 5.5 by default; the owner: not Opus reviewing Opus), with the patch, the test
that failed and the matching guide sections. It answers ``v5_required`` (the file
stays migrated; the flag and the reason are a review note) or ``fits_old_test`` (the
file becomes a test-fitting hand-off).

The call is priced and capped by the run's Budget and ledger, like every repair call
(ledger file label ``review <file>``), runs inside the run's trace, and the scorecard
says which model reviewed what. No patch is ever changed by the reviewer.
"""

from __future__ import annotations

import difflib
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Literal

from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel, Field

from migrator.cost import (
    Budget,
    CallRecord,
    LedgerRow,
    cost_usd,
    estimate_tokens,
    now_utc,
    usage_from_langchain,
)
from migrator.model_table import card_for, chat_model
from migrator.structured import ask_structured
from migrator.verify import Failure

REVIEW_MAX_TOKENS = 4000
REVIEW_EFFORT = "medium"
MAX_TEST_CHARS = 6000

ReviewVerdictName = Literal["v5_required", "fits_old_test"]

REVIEW_SYSTEM = """\
You review one patch from an automated Material UI v4 -> MUI v5 migration. The patch \
made a failing test pass, and it changes what that test looks at: accessibility \
attributes (aria-*, role, title, describeChild, tabIndex), the `component` prop or the \
rendered element. Decide which of two things it is.

- "v5_required": MUI v5 itself needs this change for the component to work as it did \
in v4. For example, v5's Slide, Fade or Grow need a child that can hold a ref, so a \
wrapper <div> around a class component is required; a renamed or moved prop is \
required. The test passing is a consequence of a correct migration.
- "fits_old_test": the change exists to satisfy a test that checks v4 behaviour v5 \
changed on purpose (class names, DOM structure, which accessibility attribute an \
element gets, default sizes). The right fix is to update the test; the patch instead \
changes the component's behaviour or accessibility so the old test passes, for \
example removing an aria-label or adding describeChild so an old title query matches.

Judge from the patch, the test and the guide sections. Answer with JSON only: \
{"verdict": "v5_required" | "fits_old_test", "reason": one sentence naming the \
deciding change}.\
"""


class ReviewAnswer(BaseModel):
    verdict: ReviewVerdictName = Field(description="v5_required or fits_old_test")
    reason: str = Field(description="One sentence naming the deciding change.")


class Review(BaseModel):
    """What the reviewer said about one flagged patch, and the call that said it."""

    verdict: ReviewVerdictName
    reason: str
    model: str
    cost_usd: float
    call: CallRecord


def patch_diff(
    touched: Sequence[str], after_rules: Mapping[str, str], current: Mapping[str, str]
) -> str:
    out = []
    for rel in touched:
        out.append(
            "".join(
                difflib.unified_diff(
                    after_rules.get(rel, "").splitlines(keepends=True),
                    current.get(rel, "").splitlines(keepends=True),
                    f"a/{rel}",
                    f"b/{rel}",
                    n=4,
                )
            )
        )
    return "\n".join(x for x in out if x)


def review_prompt(
    path: str,
    diff: str,
    flagged: Sequence[str],
    failures: Sequence[Failure],
    tests: Mapping[str, str],
    guide: Sequence[str],
) -> str:
    parts = [f"Failing file: {path}", "", "Flagged lines:", *[f"  {x}" for x in flagged]]
    parts += ["", "The patch:", "```diff", diff.rstrip(), "```", "", "The failing tests:"]
    for f in failures:
        parts.append(f"- {f.test_file} > {f.test_name}: {f.message}")
    for name, text in tests.items():
        body = text if len(text) <= MAX_TEST_CHARS else text[:MAX_TEST_CHARS] + "\n…"
        parts += ["", f"Test file {name}:", "```tsx", body.rstrip(), "```"]
    if guide:
        parts += ["", "Migration guide sections:", *guide]
    return "\n".join(parts) + "\n"


ModelFactory = Callable[[str, str | None, int], BaseChatModel]


def default_model(model: str, effort: str | None, max_tokens: int) -> BaseChatModel:
    """The reviewer's chat model from its provider (features from the model table)."""
    chat: BaseChatModel = chat_model(model, effort, max_tokens)
    return chat


def review_patch(
    prompt: str,
    *,
    model: str,
    budget: Budget,
    case: str | None,
    path: str,
    factory: ModelFactory = default_model,
) -> Review:
    """One structured-output call; raises CostCapError when the run's Budget refuses it."""
    budget.check(model, estimate_tokens(REVIEW_SYSTEM + prompt), REVIEW_MAX_TOKENS)
    chat = factory(model, card_for(model).effort(REVIEW_EFFORT), REVIEW_MAX_TOKENS)
    out = ask_structured(
        chat,
        model,
        ReviewAnswer,
        REVIEW_SYSTEM,
        prompt,
        config={"run_name": f"review {path}", "metadata": {"file": path, "reviewer": model}},
    )
    usage = usage_from_langchain(getattr(out.raw, "usage_metadata", None))
    served = out.served or model
    cost = cost_usd(model, usage)
    budget.ledger.append(
        LedgerRow(
            at=now_utc(),
            run_id=budget.run_id,
            case=case,
            file=f"review {path}",
            model=served,
            requested_model=model,
            usage=usage,
            cost_usd=cost,
        )
    )
    parsed = out.parsed
    if not isinstance(parsed, ReviewAnswer):
        raise ValueError(f"the reviewer gave no usable answer for {path}: {out.error}")
    call = CallRecord(
        model=served, requested_model=model, usage=usage, cost_usd=cost, file=f"review {path}"
    )
    return Review(
        verdict=parsed.verdict, reason=parsed.reason, model=served, cost_usd=cost, call=call
    )


def failing_tests_of(path: str, start_failures: Sequence[Failure]) -> list[Failure]:
    return [f for f in start_failures if f.file == path and f.source == "test"]


def read_tests(workspace: Path, failures: Sequence[Failure]) -> dict[str, str]:
    out: dict[str, str] = {}
    for f in failures:
        if f.test_file and f.test_file not in out and (workspace / f.test_file).is_file():
            out[f.test_file] = (workspace / f.test_file).read_text("utf-8", errors="replace")
    return out
