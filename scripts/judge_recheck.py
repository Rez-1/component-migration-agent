"""Re-check a judge model against the owner's blind ratings of the M6 OpossumUI items.

The owner rated 20 items blind in M6 (round 1 without the reference-change labels,
round 2 with them for the 12 items that needed it). The Opus 5.5 judge (prompt j2)
agreed on 10 of the 17 items it decided. This script asks another judge model the same
17 questions, using the exact j2 prompts from the judge cache, and compares.

    uv run python scripts/judge_recheck.py                 # plan: count and estimate, free
    uv run python scripts/judge_recheck.py --go --max-cost 0.50

The rating files are git-ignored (runs/m6/rating), so this only runs where M6 ran. The
new judgements are cached under their own keys (the model is part of the key) and the
report goes to runs/m6/rating/recheck-<model>.json.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from migrator.config import load_case
from migrator.cost import CostGuard, Ledger, estimate_tokens, worst_case_usd
from migrator.evals.reference import (
    JUDGE_MAX_TOKENS,
    JUDGE_MODEL,
    JUDGE_SYSTEM,
    JudgeCache,
    LLMJudge,
    judge_key,
    read_run,
)
from migrator.evals.upstream import reference_file
from migrator.model_table import ModelLevels

ROOT = Path(__file__).resolve().parent.parent
RATING = ROOT / "runs" / "m6" / "rating"
CACHE = ROOT / "runs" / "m6" / "judge-cache"
CASE = ROOT / "evals" / "m6-cases" / "opossum-ui" / "case.toml"


def owner_verdict(key: str) -> str | None:
    """The owner's verdict: round 2 (labels shown) where re-rated, else round 1."""
    for folder in (RATING / "owner2" / "ratings2", RATING / "owner" / "ratings"):
        f = folder / f"{key}.json"
        if f.is_file():
            return str(json.loads(f.read_text("utf-8"))["verdict"])
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--judge", default="balanced", help="a level or a model")
    ap.add_argument("--go", action="store_true", help="make the paid calls")
    ap.add_argument("--max-cost", type=float, default=None)
    args = ap.parse_args()

    model = ModelLevels().resolve(args.judge)
    case = load_case(CASE)
    key = json.loads((RATING / "key.json").read_text("utf-8"))
    cache = JudgeCache(CACHE)
    items = []
    for rated_key, info in sorted(key.items(), key=lambda kv: kv[1]["order"]):
        if info["by"] != "judge":
            continue  # the 3 exact matches, decided without a judge
        run = read_run(ROOT / info["run"])
        item = json.loads((RATING / f"item-{int(info['order']):02d}.json").read_text("utf-8"))
        path = item["path"]
        base, ref, final = run.base.get(path), reference_file(case, path), run.final.get(path)
        opus_key = judge_key(path, base, ref, final)  # the j2 judgement Opus made
        prompt = json.loads((CACHE / f"{opus_key}.json").read_text("utf-8"))["prompt"]
        items.append(
            {
                "order": info["order"],
                "path": path,
                "configuration": info["configuration"],
                "owner": owner_verdict(rated_key),
                "opus": info["j2_verdict"],
                "prompt": prompt,
                "key": judge_key(path, base, ref, final, model=model),
            }
        )
    pending = [i for i in items if cache.get(i["key"]) is None]
    worst = sum(
        worst_case_usd(model, estimate_tokens(JUDGE_SYSTEM + i["prompt"]), JUDGE_MAX_TOKENS)
        for i in pending
    )
    print(
        f"{len(items)} judged items; {len(pending)} not cached for {model}; worst case ${worst:.2f}"
    )
    if not args.go:
        return 0
    if pending and (args.max_cost is None or args.max_cost < worst):
        print("pass --max-cost at or above the worst case")
        return 1
    ledger = Ledger()
    judge = LLMJudge(
        "judge-recheck", CostGuard(args.max_cost or 0.01, 50.0, ledger), ledger, model=model
    )
    for i in items:
        found = cache.get(i["key"])
        if found is None:
            found = judge(i["prompt"], i["path"])
            cache.put(i["key"], found, i["prompt"])
        i["new"] = found.verdict
        i["new_reason"] = found.reason
    agree_new = sum(i["new"] == i["owner"] for i in items)
    agree_opus = sum(i["opus"] == i["owner"] for i in items)
    report = {
        "judge": model,
        "baseline_judge": JUDGE_MODEL,
        "items": len(items),
        "agree_with_owner": agree_new,
        "opus_agree_with_owner": agree_opus,
        "cost_usd": round(judge.spent, 4),
        "per_item": [{k: v for k, v in i.items() if k not in ("prompt", "key")} for i in items],
    }
    out = RATING / f"recheck-{model}.json"
    out.write_text(json.dumps(report, indent=2), "utf-8")
    print(
        f"{model}: agrees with the owner on {agree_new} of {len(items)} "
        f"(Opus: {agree_opus}); cost ${judge.spent:.3f}; report {out.relative_to(ROOT)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
