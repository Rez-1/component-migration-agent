# Metrics (dev flow)

Every number is recomputed from `results.jsonl` and the runs' scorecards
(`migrator eval summary`). With 1–2 dev cases × 2 runs, every comparison is
**directional**: the clean-run noise floor is about ±50–70 points, so read the per-trap
results and the cost alongside the headline.

- **Clean run** (headline, binary): the final verify finds no failures outside
  handed-off files.
- **Migrated share**: affected files migrated without a human.
- **Repair traps**: share of the case's agent traps scored Expected.
- **Cheating hits**: cheating-check hits on the final diff (lower is better; one hit and
  the run is not clean).
- **Regressions**: new failures in files that had none (lower is better).
- Perf: **cost** (USD from recorded tokens × the pinned price table, per model), **time**
  per run, **tool calls**. The climb target is **cost per clean run** = total cost /
  clean runs (undefined with no clean run).

Keep rule (the user's): keep a change when clean runs, repair traps Expected,
regressions and cheating hits are no worse than the best round's, and either quality
improves or cost per clean run drops.
