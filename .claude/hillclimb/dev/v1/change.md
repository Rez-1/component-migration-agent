configuration `opus-low`: Rules, then the repair agent on Claude Opus 5.5 at low effort, up to 3 attempts per failing file.

Compared with `baseline`: see change.patch.

Copied from `runs/evals/dev/v3` (M3's measured opus-low experiment on fixture revision 2,
9 November 2026) as the hill-climb's starting point; only the variant name changed
(`v3` -> `v1`, in `experiment.json` and the `scorecard` paths of `results.jsonl`).
The command logs and state snapshots were left behind (bulky, git-ignored).
