# haiku-debug on fixture revision 1 (experiment `dev/v1`, 9 November 2026)

**A debug run, not a measurement:** Claude Haiku 5.5 at high effort, 1 run, $0.03, made to check the real repair loop end to end before the measured Opus experiment. Written with `migrator eval summary dev/v1 --stable`.

It found a bug since fixed (commit `86537e0`): Search was handed off with a syntax error left in the workspace, which made Settings' suite fail to load, so Settings was handed off too and the `button-label-override` trap scored Missed. Its numbers understate what this configuration does now. The fixture changed afterwards (see `../opus-low-fixture-r1/README.md`).
