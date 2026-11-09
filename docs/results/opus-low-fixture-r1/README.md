# opus-low on fixture revision 1 (experiment `dev/v2`, 9 November 2026)

The first agent-vs-Baseline record: Claude Opus 5.5 at low effort, 1 case × 2 runs, $0.37 in total. Written with `migrator eval summary dev/v2 --stable`; the raw runs stay in the git-ignored `runs/evals/dev/v2/`.

**The fixture changed after this experiment.** In both runs the agent fixed the "human-only" trap `styles-needs-theme-provider` inside `ProfileCard.tsx`, by passing `defaultTheme: createTheme()` to `makeStyles`. That restores v4's behaviour (v4's core `makeStyles` fell back to a default theme) with a public API, so it scored Other layer here. The trap was reclassified as an agent trap, and a new human-only trap was planted (revision 2: 12 rules, 9 agent, 1 human, 1 visual-only). Numbers from this folder and from revision 2 are not directly comparable.
