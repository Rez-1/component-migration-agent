# Reference score: kubeflow-pipelines, run 2026-11-25-104630-8a5 (m8-agent-rules-stop190)

Scored against [https://github.com/kubeflow/pipelines/pull/12925](https://github.com/kubeflow/pipelines/pull/12925): 71 items (0 more out of scope).

| Verdict | Items |
|---|---|
| matches | 65 |
| other valid fix | 2 |
| wrong | 4 |
| untouched | 0 |
| out of scope | 0 |

**Silent misses** (wrong or untouched, and verify passes for the file): 3

| File | Verdict | By | Outcome | Final failures | Covered | Reason |
|---|---|---|---|---|---|---|
| `src/Css.tsx` | matches | deterministic | Migrated by agent | 0 | yes | the same as the reference after normalising formatting |
| `src/atoms/BusyButton.tsx` | matches | judge | Migrated by agent | 0 | yes | The candidate makes the same import migration to @mui/material using path imports, which is equivalent to the reference's mixed import style. |
| `src/atoms/CardTooltip.tsx` | other valid fix | judge | Migrated by agent | 0 | yes | The candidate migrates the imports and applies the transparent-tooltip styling through componentsProps.tooltip.sx, which looks the same as the reference. Removing `interactive` is equivalent because v5 tooltips are interactive by default, so `disableInteractive={false}` is just the default. |
| `src/atoms/HelpButton.tsx` | matches | judge | Migrated by agent | 0 | yes | The candidate makes the same import migration (@mui/material/IconButton and @mui/icons-material/Help) and adds size="large" to IconButton, which is equivalent to the reference. |
| `src/atoms/IconWithTooltip.tsx` | matches | judge | Migrated by agent | 0 | yes | The candidate migrates both imports to @mui/material; using the default path import for Tooltip is equivalent to the reference's named import. |
| `src/atoms/Input.tsx` | matches | judge | Migrated by agent | 0 | yes | Candidate updates the import path to @mui/material/TextField, keeping the default TextField and OutlinedTextFieldProps; this is equivalent to the reference's split imports. |
| `src/atoms/MD2Tabs.tsx` | matches | judge | Migrated by agent | 0 | yes | The candidate swaps the same Button and Tooltip imports to @mui/material/Button and @mui/material/Tooltip, which is equivalent to the reference's named import from @mui/material. |
| `src/components/Banner.tsx` | matches | judge | Migrated by agent | 0 | yes | The candidate makes the same package migration in R1, using per-component @mui/material path imports instead of one named import, which is equivalent. |
| `src/components/CollapseButton.tsx` | matches | judge | Migrated by agent | 0 | yes | The candidate updates both imports to @mui/material/Button and @mui/icons-material/ArrowDropUp, which is equivalent to the reference's named import from @mui/material. |
| `src/components/CollapseButtonSingle.tsx` | matches | judge | Migrated by agent | 0 | yes | The candidate makes the same import path changes as R1, using the default import from '@mui/material/Button' rather than the named import from '@mui/material', which is equivalent. |
| `src/components/CustomTable.tsx` | matches | judge | Migrated by agent | 0 | yes | The candidate migrates every import to @mui/material and @mui/icons-material, as R1 does. It also adds size="large" to all three IconButtons, as R5 and R6 do. The only differences are import style and quote and bracket formatting. |
| `src/components/CustomTableNameColumn.tsx` | matches | judge | Migrated by agent | 0 | yes | The candidate migrates the Tooltip import to @mui/material/Tooltip, which is equivalent to the reference's named import from @mui/material. |
| `src/components/CustomTableRow.tsx` | matches | judge | Migrated by agent | 0 | yes | The candidate makes the same import path changes. It uses the path import '@mui/material/Tooltip' where the reference uses a named import from '@mui/material', which is equivalent. |
| `src/components/ExperimentList.tsx` | matches | judge | Migrated by agent | 0 | yes | The candidate imports Tooltip from '@mui/material/Tooltip' (default import), which is equivalent to the reference's named import from '@mui/material'. |
| `src/components/Graph.tsx` | matches | judge | Migrated by agent | 0 | yes | The candidate changes the Tooltip import to the default path import @mui/material/Tooltip, which is equivalent to the reference's named import from @mui/material. |
| `src/components/NewRunParameters.tsx` | matches | judge | Migrated by agent | 0 | yes | The candidate migrates the same three imports to @mui/material using per-component paths, which is equivalent to the reference's combined named import. |
| `src/components/NewRunParametersV2.tsx` | matches | deterministic | Migrated by agent | 0 | yes | the same as the reference after normalising formatting |
| `src/components/PipelinesDialog.tsx` | matches | judge | Migrated by agent | 0 | yes | The candidate swaps the four @material-ui/core imports for equivalent @mui/material path imports. This is the same migration as R1 and R2, only in a different import style. |
| `src/components/PipelinesDialogV2.tsx` | matches | judge | Migrated by agent | 0 | yes | The candidate swaps the same four imports to @mui/material path imports, which is equivalent to the reference's combined named import. |
| `src/components/PlotCard.tsx` | matches | judge | Migrated by agent | 0 | yes | The candidate makes the same import path changes, using per-component default imports from @mui/material instead of a combined named import. The two are equivalent. |
| `src/components/PrivateSharedSelector.tsx` | matches | judge | Migrated by agent | 0 | yes | The candidate swaps the same three imports to @mui/material path imports, which is equivalent to the reference's combined named import. |
| `src/components/ReduceGraphSwitch.tsx` | matches | judge | Migrated by agent | 0 | yes | The candidate makes the same @material-ui/core to @mui/material import-path migration using per-component default imports, which is equivalent to the reference's combined named import. |
| `src/components/Router.tsx` | matches | judge | Migrated by agent | 0 | yes | The candidate converts all the @material-ui/core imports to equivalent @mui/material path imports. This is the same migration as R1 and R2, only with a different import style. |
| `src/components/SideNav.tsx` | matches | judge | Migrated by agent | 0 | yes | The candidate makes the same import changes, using per-component paths for @mui/material, which is equivalent to the reference's combined import. It also adds size="large" to the chevron IconButton as R3 does. |
| `src/components/SidePanel.tsx` | other valid fix | judge | Migrated by agent | 0 | yes | Candidate updates the imports (R1) and wraps Resizable in a div for Slide (R2). Its wrapper has extra absolute-positioned styling with pointerEvents none and a zIndex, which is more than the reference's plain div. It still gives Slide a ref-capable child and should render and behave the same, though the extra positioning is a small risk. |
| `src/components/Toolbar.tsx` | matches | judge | Migrated by agent | 0 | yes | The candidate updates the imports to @mui/material and @mui/icons-material, using per-component paths, which is equivalent to the reference's named import. It also adds size="large" to the IconButton, as R2 does. |
| `src/components/Trigger.tsx` | matches | judge | Migrated by agent | 0 | yes | The candidate swaps the four @material-ui/core path imports for the equivalent @mui/material path imports. This is the same migration as R1/R2 in a different but equivalent import style. |
| `src/components/TwoLevelDropdown.tsx` | matches | judge | Migrated by agent | 0 | yes | The candidate makes the same import changes as R1. Its added `describeChild` props on Tooltip are extra, but they only affect accessibility semantics and do not break anything or change how the screen looks. |
| `src/components/UploadPipelineDialog.tsx` | matches | judge | Migrated by agent | 0 | yes | The candidate converts every @material-ui/core import to the equivalent @mui/material path imports; this is equivalent to the reference's consolidated named import. |
| `src/components/graph/ArtifactNode.tsx` | matches | deterministic | Migrated by agent | 0 | yes | the same as the reference after normalising formatting |
| `src/components/graph/ExecutionNode.tsx` | matches | deterministic | Migrated by agent | 0 | yes | the same as the reference after normalising formatting |
| `src/components/graph/SubDagLayer.tsx` | matches | judge | Migrated by agent | 0 | yes | The candidate makes the same import changes as R1 (grey from '@mui/material/colors', icon from '@mui/icons-material/ArrowRightAlt'). It also removed the license header, which is unrelated to the migration. |
| `src/components/graph/SubDagNode.tsx` | matches | deterministic | Migrated by agent | 0 | no | the same as the reference after normalising formatting |
| `src/components/navigators/PipelineVersionCard.tsx` | wrong **(silent miss)** | judge | Migrated by agent | 0 | yes | The candidate migrates the imports (R1) but omits variant='standard' on FormControl and Select (R2). In v5 the Select defaults to outlined, so the look changes from v4. |
| `src/components/tabs/RuntimeNodeDetailsV2.tsx` | matches | deterministic | Migrated by agent | 0 | yes | the same as the reference after normalising formatting |
| `src/components/tabs/StaticNodeDetailsV2.tsx` | matches | deterministic | Migrated by agent | 0 | yes | the same as the reference after normalising formatting |
| `src/components/viewers/MetricsDropdown.tsx` | matches | judge | Migrated by agent | 0 | yes | The candidate swaps the v4 default import for the equivalent @mui/material/CircularProgress import, which is the same change as R1 and R2 combined. |
| `src/components/viewers/MetricsVisualizations.tsx` | matches | judge | Migrated by agent | 0 | yes | The candidate updates the icon import and moves Tooltip to @mui/material/Tooltip. This is equivalent to the reference's named import from @mui/material. |
| `src/components/viewers/PagedTable.tsx` | matches | judge | Migrated by agent | 0 | yes | The candidate converts every @material-ui/core path import to the equivalent @mui/material path import, which is the same migration as R1 with a different but equivalent import style. |
| `src/components/viewers/Tensorboard.tsx` | wrong **(silent miss)** | judge | Migrated by agent | 0 | yes | The candidate matches R1-R3, but it omits R4's variant='standard' on FormControl and Select. In v5 the select would default to outlined and look different from v4. |
| `src/components/viewers/VisualizationCreator.tsx` | wrong | judge | Unmigrated | 10 |  | The candidate matches R1 and R3, but it omits R2. Without variant='standard' on FormControl and Select, v5 renders the select as outlined instead of the v4 standard look. |
| `src/icons/statusCached.tsx` | matches | deterministic | Migrated by agent | 0 | yes | the same as the reference after normalising formatting |
| `src/index.tsx` | matches | deterministic | Migrated by agent | 0 | no | the same as the reference after normalising formatting |
| `src/lib/Buttons.ts` | matches | deterministic | Migrated by agent | 0 | yes | the same as the reference after normalising formatting |
| `src/lib/WorkflowParser.ts` | matches | deterministic | Migrated by agent | 0 | yes | the same as the reference after normalising formatting |
| `src/mlmd/Css.tsx` | matches | deterministic | Migrated by agent | 0 | yes | the same as the reference after normalising formatting |
| `src/mlmd/LineageActionBar.tsx` | matches | judge | Migrated by agent | 0 | yes | The candidate makes the same import migrations as R1: icons come from @mui/icons-material, and Button and grey come from @mui/material. It uses a default import for Button instead of a named one, which is equivalent. |
| `src/mlmd/LineageCard.tsx` | matches | deterministic | Migrated by agent | 0 | no | the same as the reference after normalising formatting |
| `src/mlmd/LineageCardColumn.tsx` | matches | judge | Migrated by agent | 0 | no | The candidate makes the same import change, using `import { grey } from '@mui/material/colors'`. It also removed the license header, but that has no functional effect. |
| `src/mlmd/LineageView.tsx` | matches | judge | Migrated by agent | 0 | no | The candidate swaps the CircularProgress import to @mui/material/CircularProgress, a path import equivalent to the reference's named import from @mui/material. |
| `src/pages/ArtifactDetails.tsx` | matches | deterministic | Migrated by agent | 0 | yes | the same as the reference after normalising formatting |
| `src/pages/CompareV2.tsx` | matches | judge | Migrated by agent | 0 | yes | The candidate swaps the CircularProgress import to '@mui/material/CircularProgress', which is equivalent to the reference's named import from '@mui/material'. |
| `src/pages/ExecutionDetails.tsx` | matches | deterministic | Migrated by agent | 0 | no | the same as the reference after normalising formatting |
| `src/pages/ExperimentDetails.tsx` | matches | judge | Migrated by agent | 0 | yes | The candidate moves every @material-ui/core import to the matching @mui/material path import and switches the icon to @mui/icons-material/Launch. The path-style imports are equivalent to the reference's combined named import. |
| `src/pages/ExperimentList.tsx` | matches | judge | Migrated by agent | 0 | yes | The candidate changes the Tooltip import to @mui/material/Tooltip, which is equivalent to the reference's named import from @mui/material. |
| `src/pages/FrontendFeatures.tsx` | matches | judge | Migrated by agent | 0 | no | The candidate switches every import to @mui/material, using per-component default imports instead of one combined import, which is equivalent. |
| `src/pages/NewExperiment.tsx` | matches | judge | Migrated by agent | 0 | yes | The candidate moves both the Button and TextFieldProps imports to @mui/material paths. Importing Button from '@mui/material/Button' is equivalent to the reference's named import from '@mui/material'. |
| `src/pages/NewPipelineVersion.tsx` | matches | judge | Migrated by agent | 0 | yes | The candidate moves all the same imports to @mui/material using per-component paths, which is equivalent to the reference's combined import. |
| `src/pages/NewRun.tsx` | matches | judge | Migrated by agent | 0 | yes | The candidate migrates all the same imports to @mui/material, using per-component paths instead of a combined named import. This is equivalent, with no other v5 changes needed. |
| `src/pages/NewRunV2.tsx` | matches | deterministic | Migrated by agent | 0 | yes | the same as the reference after normalising formatting |
| `src/pages/Page.tsx` | matches | deterministic | Migrated by agent | 0 | yes | the same as the reference after normalising formatting |
| `src/pages/PipelineDetailsV1.tsx` | wrong **(silent miss)** | judge | Migrated by agent | 0 | yes | The candidate migrates the imports correctly (R1, R2), but omits R3, so the version selector renders as outlined in v5 instead of the v4 standard look. |
| `src/pages/PipelineList.tsx` | matches | judge | Migrated by agent | 0 | yes | The candidate replaces the v4 Tooltip import with the equivalent '@mui/material/Tooltip' default import, which is the same migration as the reference's named import from '@mui/material'. |
| `src/pages/PipelineVersionList.tsx` | matches | judge | Migrated by agent | 0 | yes | The candidate swaps the Tooltip import to '@mui/material/Tooltip', which is equivalent to the reference's named import from '@mui/material' (R1/R2). |
| `src/pages/RecurringRunList.tsx` | matches | judge | Migrated by agent | 0 | yes | Candidate changes the Tooltip import to the equivalent default path import '@mui/material/Tooltip', which is the same migration as R1. |
| `src/pages/RecurringRunsManager.tsx` | matches | deterministic | Migrated by agent | 0 | yes | the same as the reference after normalising formatting |
| `src/pages/RunDetails.tsx` | matches | judge | Migrated by agent | 0 | yes | The candidate updates both imports to @mui/material/CircularProgress and @mui/icons-material/InfoOutlined, which is equivalent to the reference's named import from @mui/material. |
| `src/pages/RunList.tsx` | matches | judge | Migrated by agent | 0 | yes | The candidate imports Tooltip from '@mui/material/Tooltip', which is equivalent to the reference's named import from '@mui/material'. |
| `src/pages/Status.tsx` | matches | judge | Migrated by agent | 0 | yes | The candidate makes the same icon import changes and imports Tooltip from '@mui/material/Tooltip', which is equivalent to the reference's named import from '@mui/material'. |
| `src/pages/StatusV2.tsx` | matches | judge | Migrated by agent | 0 | yes | The candidate makes the same icon import changes and imports Tooltip from '@mui/material/Tooltip', which is equivalent to the reference's named import from '@mui/material'. |
| `src/pages/functional_components/NewExperimentFC.tsx` | matches | judge | Migrated by agent | 0 | yes | The candidate swaps the Button import to '@mui/material/Button', a default import from a subpath that is equivalent to the reference's named import from '@mui/material'. |

## Reference changes set aside as out of scope

- `src/components/CustomTable.tsx`: R2: Blank line removed before the Header comment
- `src/components/CustomTable.tsx`: R3: Blank line removed before the Body comment
- `src/components/CustomTable.tsx`: R4: Blank line removed before the Footer comment
- `src/components/viewers/VisualizationCreator.tsx`: R4: Removed a blank line

## Test files the reference changed (expected hand-offs)

- `src/atoms/BusyButton.test.tsx`
- `src/atoms/IconWithTooltip.test.tsx`
- `src/atoms/__snapshots__/BusyButton.test.tsx.snap`
- `src/atoms/__snapshots__/IconWithTooltip.test.tsx.snap`
- `src/atoms/__snapshots__/Input.test.tsx.snap`
- `src/atoms/__snapshots__/MD2Tabs.test.tsx.snap`
- `src/components/CustomTable.test.tsx`
- `src/components/Graph.test.tsx`
- `src/components/Toolbar.test.tsx`
- `src/components/__snapshots__/Banner.test.tsx.snap`
- `src/components/__snapshots__/CollapseButton.test.tsx.snap`
- `src/components/__snapshots__/CustomTable.test.tsx.snap`
- `src/components/__snapshots__/CustomTableRow.test.tsx.snap`
- `src/components/__snapshots__/ExperimentList.test.tsx.snap`
- `src/components/__snapshots__/Graph.test.tsx.snap`
- `src/components/__snapshots__/NewRunParameters.test.tsx.snap`
- `src/components/__snapshots__/PipelinesDialog.test.tsx.snap`
- `src/components/__snapshots__/PlotCard.test.tsx.snap`
- `src/components/__snapshots__/PrivateSharedSelector.test.tsx.snap`
- `src/components/__snapshots__/Router.test.tsx.snap`
- `src/components/__snapshots__/SideNav.test.tsx.snap`
- `src/components/__snapshots__/Toolbar.test.tsx.snap`
- `src/components/__snapshots__/Trigger.test.tsx.snap`
- `src/components/navigators/PipelineVersionCard.test.tsx`
- `src/components/viewers/MetricsDropdown.test.tsx`
- `src/components/viewers/VisualizationCreator.test.tsx`
- `src/components/viewers/__snapshots__/PagedTable.test.tsx.snap`
- `src/components/viewers/__snapshots__/Tensorboard.test.tsx.snap`
- `src/components/viewers/__snapshots__/ViewerContainer.test.tsx.snap`
- `src/components/viewers/__snapshots__/VisualizationCreator.test.tsx.snap`
- `src/lib/WorkflowParser.test.ts`
- `src/mlmd/__snapshots__/LineageActionBar.test.tsx.snap`
- `src/pages/ArtifactList.test.tsx`
- `src/pages/CompareV2.test.tsx`
- `src/pages/ExecutionList.test.tsx`
- `src/pages/NewPipelineVersion.test.tsx`
- `src/pages/NewRun.test.tsx`
- `src/pages/NewRunV2.test.tsx`
- `src/pages/PipelineDetailsV1.test.tsx`
- `src/pages/RunDetails.test.tsx`
- `src/pages/__snapshots__/AllExperimentsAndArchive.test.tsx.snap`
- `src/pages/__snapshots__/AllRunsAndArchive.test.tsx.snap`
- `src/pages/__snapshots__/CompareV1.test.tsx.snap`
- `src/pages/__snapshots__/ExperimentDetails.test.tsx.snap`
- `src/pages/__snapshots__/ExperimentList.test.tsx.snap`
- `src/pages/__snapshots__/NewExperiment.test.tsx.snap`
- `src/pages/__snapshots__/NewPipelineVersion.test.tsx.snap`
- `src/pages/__snapshots__/NewRun.test.tsx.snap`
- `src/pages/__snapshots__/PipelineList.test.tsx.snap`
- `src/pages/__snapshots__/PipelineVersionList.test.tsx.snap`
- `src/pages/__snapshots__/PrivateAndSharedPipelines.test.tsx.snap`
- `src/pages/__snapshots__/ResourceSelector.test.tsx.snap`
- `src/pages/__snapshots__/RunDetails.test.tsx.snap`
- `src/pages/__snapshots__/RunList.test.tsx.snap`
- `src/pages/__snapshots__/Status.test.tsx.snap`
- `src/pages/__snapshots__/StatusV2.test.tsx.snap`

## Other files the reference changed (not scored)

- `package-lock.json`
- `package.json`

Judge: 6 new calls, $0.04.
