# Reference score: kubeflow-pipelines, run 2026-11-16-121724-0df (m6-baseline)

Scored against [https://github.com/kubeflow/pipelines/pull/12925](https://github.com/kubeflow/pipelines/pull/12925): 71 items (0 more out of scope).

| Verdict | Items |
|---|---|
| matches | 65 |
| other valid fix | 2 |
| wrong | 4 |
| untouched | 0 |
| out of scope | 0 |

**Silent misses** (wrong or untouched, and verify passes for the file): 0

| File | Verdict | By | Outcome | Final failures | Covered | Reason |
|---|---|---|---|---|---|---|
| `src/Css.tsx` | other valid fix | judge | Migrated by rules | 0 | yes | The candidate wraps the v4 theme in adaptV4Theme, the official MUI v5 compatibility shim, which converts overrides to components.styleOverrides. The reference rewrites the theme by hand. Behavior should be the same, with one risk: adaptV4Theme may not translate the `$disabled`, `$focused` and `$active` selectors, which the reference replaced explicitly. It is also deprecated and removed in v6. |
| `src/atoms/BusyButton.tsx` | matches | judge | Migrated by rules | 0 | yes | The candidate migrates the same imports to @mui/material using per-component paths, which is equivalent to the reference's import style. |
| `src/atoms/CardTooltip.tsx` | wrong | judge | Unmigrated | 1 |  | The candidate migrates imports and keeps withStyles from @mui/styles, which is acceptable, but it leaves `interactive={true}` on Tooltip (R2). v5 removed that prop, so it is a missing required change and will fail to type-check. |
| `src/atoms/HelpButton.tsx` | matches | judge | Migrated by rules | 0 | yes | The candidate makes the same import changes (an equivalent path import for IconButton) and adds size='large' to IconButton, as the reference does. |
| `src/atoms/IconWithTooltip.tsx` | matches | judge | Migrated by rules | 0 | yes | The candidate makes the same import path changes to @mui/material; using a default import for Tooltip from '@mui/material/Tooltip' is equivalent to the reference's named import. |
| `src/atoms/Input.tsx` | matches | judge | Migrated by rules | 0 | yes | The candidate changes the import path to @mui/material/TextField, keeping the default TextField import and the OutlinedTextFieldProps type. This is equivalent to the reference's import change. |
| `src/atoms/MD2Tabs.tsx` | matches | judge | Migrated by rules | 0 | yes | The candidate switches both imports to @mui/material path imports, which is equivalent to the reference's named import from @mui/material. |
| `src/components/Banner.tsx` | matches | judge | Migrated by rules | 0 | yes | The candidate makes the same import path migration, using per-component @mui/material/* default imports instead of a combined named import, which is equivalent. |
| `src/components/CollapseButton.tsx` | matches | judge | Migrated by rules | 0 | yes | The candidate makes the same import path migration; using the path import '@mui/material/Button' instead of the named import is equivalent. |
| `src/components/CollapseButtonSingle.tsx` | matches | judge | Migrated by rules | 0 | yes | The candidate updates both imports to @mui/material/Button and @mui/icons-material/ArrowDropUp, which is equivalent to the reference's named import from @mui/material. |
| `src/components/CustomTable.tsx` | matches | judge | Unmigrated | 20 |  | The candidate migrates all imports to @mui/material and @mui/icons-material (path imports instead of a combined import, which is equivalent) and adds size='large' to all three IconButtons as in R5 and R6. Only the blank-line hunks are missing, and those are unrelated. |
| `src/components/CustomTableNameColumn.tsx` | matches | judge | Migrated by rules | 0 | yes | The candidate imports Tooltip from '@mui/material/Tooltip', a default import from the path-specific module. That is equivalent to the reference's named import from '@mui/material'. |
| `src/components/CustomTableRow.tsx` | matches | judge | Migrated by rules | 0 | yes | The candidate makes the same import path changes; importing Tooltip from '@mui/material/Tooltip' is equivalent to the reference's named import from '@mui/material'. |
| `src/components/ExperimentList.tsx` | matches | judge | Migrated by rules | 0 | yes | The candidate imports Tooltip from '@mui/material/Tooltip', a default path import equivalent to the reference's named import from '@mui/material'. |
| `src/components/Graph.tsx` | matches | judge | Migrated by rules | 0 | yes | The candidate changes the import to the v5 path @mui/material/Tooltip. That is equivalent to the reference's named import from @mui/material. |
| `src/components/NewRunParameters.tsx` | matches | judge | Migrated by rules | 0 | yes | The candidate swaps the same three imports to @mui/material path imports, which is equivalent to the reference's combined named import. |
| `src/components/NewRunParametersV2.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/components/PipelinesDialog.tsx` | matches | judge | Migrated by rules | 0 | yes | The candidate swaps the four @material-ui/core imports for equivalent @mui/material path imports. Only the import style differs from the reference's single named import, and the result is the same. |
| `src/components/PipelinesDialogV2.tsx` | matches | judge | Migrated by rules | 0 | yes | The candidate swaps the same four imports to @mui/material per-component paths, which is equivalent to the reference's combined named import. |
| `src/components/PlotCard.tsx` | matches | judge | Migrated by rules | 0 | yes | The candidate makes the same import path migration using per-component imports from @mui/material and @mui/icons-material, which is equivalent to the reference's named import. |
| `src/components/PrivateSharedSelector.tsx` | matches | judge | Migrated by rules | 0 | yes | The candidate switches the same three imports to @mui/material path imports, which is equivalent to the reference's combined named import. |
| `src/components/ReduceGraphSwitch.tsx` | matches | judge | Migrated by rules | 0 | yes | The candidate makes the same import path migration to @mui/material using per-component default imports, which is equivalent to the reference's named import. |
| `src/components/Router.tsx` | matches | judge | Migrated by rules | 0 | yes | The candidate moves every import from @material-ui/core to @mui/material per-component paths. This is equivalent to the reference's combined import; no styling changes are needed. |
| `src/components/SideNav.tsx` | matches | judge | Migrated by rules | 0 | yes | The candidate makes the same import changes, using per-component @mui/material paths instead of a combined import, which is equivalent. It also adds size='large' to the chevron IconButton, as R3 does. |
| `src/components/SidePanel.tsx` | wrong | judge | Unmigrated | 1 |  | The candidate matches R1 with equivalent per-component imports. It omits R2's wrapper div, so Slide gets a Resizable child that may not forward a ref, and the slide transition can break. |
| `src/components/Toolbar.tsx` | matches | judge | Migrated by rules | 0 | yes | The candidate migrates the imports to @mui/material (per-component paths) and @mui/icons-material, which is equivalent to R1, and adds size='large' to the IconButton exactly as in R2. |
| `src/components/Trigger.tsx` | matches | judge | Migrated by rules | 0 | yes | The candidate moves the same four components to @mui/material using per-component default imports, which is equivalent to the reference's combined named import. |
| `src/components/TwoLevelDropdown.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/components/UploadPipelineDialog.tsx` | matches | judge | Migrated by rules | 0 | yes | The candidate converts all the same imports to @mui/material path imports, which is equivalent to the reference's consolidated named import; no styling changes were needed. |
| `src/components/graph/ArtifactNode.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/components/graph/ExecutionNode.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/components/graph/SubDagLayer.tsx` | matches | judge | Migrated by rules | 0 | yes | The candidate makes the same import changes as R1 (grey from '@mui/material/colors', icon from '@mui/icons-material'). It also removed the license header, which is unrelated to the migration and does not affect behavior. |
| `src/components/graph/SubDagNode.tsx` | matches | deterministic | Migrated by rules | 0 | no | the same as the reference after normalising formatting |
| `src/components/navigators/PipelineVersionCard.tsx` | matches | judge | Unmigrated | 1 |  | The candidate uses per-component @mui/material imports, which are equivalent to the reference's consolidated import (R1), and adds the same variant='standard' on FormControl and Select (R2). |
| `src/components/tabs/RuntimeNodeDetailsV2.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/components/tabs/StaticNodeDetailsV2.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/components/viewers/MetricsDropdown.tsx` | matches | judge | Unmigrated | 5 |  | The candidate swaps the v4 default import for the equivalent '@mui/material/CircularProgress' default import. This is the same migration as R1 and R2, just with a different import style. |
| `src/components/viewers/MetricsVisualizations.tsx` | matches | judge | Migrated by rules | 0 | yes | The candidate migrates both the icon and Tooltip imports to the v5 packages. Importing Tooltip from @mui/material/Tooltip instead of the @mui/material barrel is equivalent. |
| `src/components/viewers/PagedTable.tsx` | matches | judge | Migrated by rules | 0 | yes | The candidate moves every import to @mui/material/<Component> paths, which is equivalent to the reference's single named import from @mui/material. |
| `src/components/viewers/Tensorboard.tsx` | wrong | judge | Unmigrated | 1 |  | The candidate matches R1 imports (per-component paths), R3 and R4. It omits R2: handleImageSelect keeps the v4 React.ChangeEvent<{name?, value: unknown}> type, which no longer type-checks against v5 Select's onChange (SelectChangeEvent). |
| `src/components/viewers/VisualizationCreator.tsx` | wrong | judge | Unmigrated | 11 |  | The candidate matches R1 (imports) and R2 (variant='standard'). It leaves the Select onChange typed as React.ChangeEvent<{name?: string; value: unknown}> instead of SelectChangeEvent (R3). In v5 that type no longer fits Select's onChange, so the file likely fails type-checking. |
| `src/icons/statusCached.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/index.tsx` | matches | judge | Migrated by rules | 0 | no | The candidate makes the same import change and the same StyledEngineProvider injectFirst wrapping as R1 and R2. Its extra DefaultTheme module augmentation is a harmless typing addition. |
| `src/lib/Buttons.ts` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/lib/WorkflowParser.ts` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/mlmd/Css.tsx` | other valid fix | judge | Migrated by rules | 0 | yes | The candidate updates the import and wraps the unchanged v4 theme in adaptV4Theme, which converts overrides to styleOverrides and rewrites the $-selectors at runtime. It is a documented valid v5 migration path and behaves the same as the reference, though it keeps the deprecated v4 shape and is less idiomatic. |
| `src/mlmd/LineageActionBar.tsx` | matches | judge | Migrated by rules | 0 | yes | The candidate makes the same import migrations as R1: icons come from @mui/icons-material, and Button and grey from @mui/material, with only a different import style for Button. |
| `src/mlmd/LineageCard.tsx` | matches | deterministic | Migrated by rules | 0 | no | the same as the reference after normalising formatting |
| `src/mlmd/LineageCardColumn.tsx` | matches | judge | Migrated by rules | 0 | no | The candidate makes the same grey import change to '@mui/material/colors' as R1. It also removes the license header, which is a harmless comment-only change. |
| `src/mlmd/LineageView.tsx` | matches | judge | Migrated by rules | 0 | no | The candidate swaps the import to @mui/material/CircularProgress, a default path import that is equivalent to the reference's named import from @mui/material. |
| `src/pages/ArtifactDetails.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/pages/CompareV2.tsx` | matches | judge | Migrated by rules | 0 | yes | The candidate changes the CircularProgress import to '@mui/material/CircularProgress', which is equivalent to the reference's named import from '@mui/material'. |
| `src/pages/ExecutionDetails.tsx` | matches | deterministic | Migrated by rules | 0 | no | the same as the reference after normalising formatting |
| `src/pages/ExperimentDetails.tsx` | matches | judge | Migrated by rules | 0 | yes | The candidate moves every @material-ui/core import to @mui/material path imports and the icon to @mui/icons-material/Launch. This is equivalent to the reference's combined named import. |
| `src/pages/ExperimentList.tsx` | matches | judge | Migrated by rules | 0 | yes | The candidate changes the Tooltip import to the default import from '@mui/material/Tooltip', which is equivalent to the reference's named import from '@mui/material'. |
| `src/pages/FrontendFeatures.tsx` | matches | judge | Migrated by rules | 0 | no | The candidate changes the same imports to @mui/material, using per-component paths instead of one consolidated import. The two forms are equivalent. |
| `src/pages/NewExperiment.tsx` | matches | judge | Migrated by rules | 0 | yes | The candidate moves Button to @mui/material/Button and updates TextFieldProps to @mui/material/TextField. This is the same migration as R1 and R2, with a different but equivalent import style for Button. |
| `src/pages/NewPipelineVersion.tsx` | matches | judge | Migrated by rules | 0 | yes | The candidate moves the same components (Button, FormControlLabel, InputAdornment, Radio, TextFieldProps) to @mui/material, using per-component import paths instead of the reference's combined import, which is equivalent. |
| `src/pages/NewRun.tsx` | matches | judge | Migrated by rules | 0 | yes | The candidate migrates all the same imports to @mui/material using per-component paths instead of a combined named import, which is equivalent. |
| `src/pages/NewRunV2.tsx` | matches | deterministic | Unmigrated | 1 |  | the same as the reference after normalising formatting |
| `src/pages/Page.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/pages/PipelineDetailsV1.tsx` | matches | judge | Unmigrated | 13 |  | The candidate migrates all imports to @mui/material and @mui/icons-material (an equivalent per-component import style) and adds variant='standard' to both FormControl and Select, as the reference does. |
| `src/pages/PipelineList.tsx` | matches | judge | Migrated by rules | 0 | yes | The candidate swaps the v4 Tooltip import for `@mui/material/Tooltip`, which is equivalent to the reference's named import from `@mui/material`; only the import style differs. |
| `src/pages/PipelineVersionList.tsx` | matches | judge | Migrated by rules | 0 | yes | The candidate swaps the import to '@mui/material/Tooltip', which is equivalent to the reference's named import from '@mui/material' (R1/R2). |
| `src/pages/RecurringRunList.tsx` | matches | judge | Migrated by rules | 0 | yes | The candidate changes the Tooltip import to the v5 path @mui/material/Tooltip, which is equivalent to the reference's named import from @mui/material. |
| `src/pages/RecurringRunsManager.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/pages/RunDetails.tsx` | matches | judge | Unmigrated | 45 |  | The candidate moves both imports to @mui/material/CircularProgress and @mui/icons-material/InfoOutlined, which is equivalent to the reference's import changes (path import vs named import). |
| `src/pages/RunList.tsx` | matches | judge | Migrated by rules | 0 | yes | The candidate uses the default import from '@mui/material/Tooltip', which is equivalent to the reference's named import from '@mui/material'. |
| `src/pages/Status.tsx` | matches | judge | Migrated by rules | 0 | yes | The candidate makes the same icon import changes and imports Tooltip from '@mui/material/Tooltip', which is equivalent to the reference's named import from '@mui/material'. |
| `src/pages/StatusV2.tsx` | matches | judge | Migrated by rules | 0 | yes | The candidate makes the same icon import changes and imports Tooltip from '@mui/material/Tooltip', which is equivalent to the reference's named import from '@mui/material'. |
| `src/pages/functional_components/NewExperimentFC.tsx` | matches | judge | Migrated by rules | 0 | yes | The candidate replaces the v4 Button import with '@mui/material/Button', which is equivalent to the reference's named import from '@mui/material'. Both migrate the import path the same way. |

## Reference changes set aside as out of scope

- `src/components/CustomTable.tsx`: R2: Blank line removal before Header comment
- `src/components/CustomTable.tsx`: R3: Blank line removal before Body comment
- `src/components/CustomTable.tsx`: R4: Blank line removal before Footer comment
- `src/components/viewers/VisualizationCreator.tsx`: R4: Blank line removed

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

Judge: 0 new calls, $0.00.
