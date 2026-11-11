# Reference score: kubeflow-pipelines, run 2026-11-10-152320-e61 (m6-baseline)

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
| `src/Css.tsx` | other valid fix | judge | Migrated by rules | 0 | yes | The candidate wraps the v4 theme in adaptV4Theme instead of restructuring it as in R2. adaptV4Theme converts overrides to styleOverrides and the $state selectors, so the result is equivalent, though deprecated. |
| `src/atoms/BusyButton.tsx` | matches | judge | Migrated by rules | 0 | yes | The candidate updates the same imports to @mui/material using path imports. That is equivalent to R1's named imports. |
| `src/atoms/CardTooltip.tsx` | wrong | judge | Unmigrated | 1 |  | Candidate updates imports (R1 equivalent with withStyles on @mui/styles) but leaves the removed `interactive` prop instead of R2's v5 equivalent. In v5, tooltips are interactive by default, so behaviour would match, but `interactive` no longer exists on TooltipProps and would cause a TypeScript error. |
| `src/atoms/HelpButton.tsx` | matches | judge | Migrated by rules | 0 | yes | The candidate updates the imports equivalently (default import path instead of a named import) and adds the same size='large' as R1. |
| `src/atoms/IconWithTooltip.tsx` | matches | judge | Migrated by rules | 0 | yes | The candidate moves both imports to @mui/material. Using the default path import for Tooltip is equivalent to the reference's named import (R1). |
| `src/atoms/Input.tsx` | matches | judge | Migrated by rules | 0 | yes | The candidate imports both TextField and OutlinedTextFieldProps from @mui/material/TextField, which is equivalent to the reference's R1 import change. |
| `src/atoms/MD2Tabs.tsx` | matches | judge | Migrated by rules | 0 | yes | Candidate updates the same imports to @mui/material using path imports, which is equivalent to R1. |
| `src/components/Banner.tsx` | matches | judge | Migrated by rules | 0 | yes | The candidate updates the same imports to @mui/material and @mui/icons-material, using per-component default imports. These are equivalent to the reference's named imports for R1. |
| `src/components/CollapseButton.tsx` | matches | judge | Migrated by rules | 0 | yes | The candidate updates both imports to @mui/material and @mui/icons-material. The default-path import style it uses is equivalent to the reference's named import from @mui/material. |
| `src/components/CollapseButtonSingle.tsx` | matches | judge | Migrated by rules | 0 | yes | R1's import path changes are reproduced by the candidate with an equivalent default-import style. |
| `src/components/CustomTable.tsx` | matches | judge | Unmigrated | 20 |  | The candidate updates the imports equivalently (R1, using default-path imports) and adds the same size='large' props (R5, R6). The skipped hunks only remove blank lines. |
| `src/components/CustomTableNameColumn.tsx` | matches | judge | Migrated by rules | 0 | yes | R1's import change is matched by an equivalent default import from @mui/material/Tooltip. |
| `src/components/CustomTableRow.tsx` | matches | judge | Migrated by rules | 0 | yes | R1's import changes are reproduced equivalently; the candidate uses a default path import instead of a named import. |
| `src/components/ExperimentList.tsx` | matches | judge | Migrated by rules | 0 | yes | R1 is matched by the candidate's equivalent default import from @mui/material/Tooltip. |
| `src/components/Graph.tsx` | matches | judge | Migrated by rules | 0 | yes | R1 import path change is matched by an equivalent default import from @mui/material/Tooltip. |
| `src/components/NewRunParameters.tsx` | matches | judge | Migrated by rules | 0 | yes | The candidate makes the same import migration to @mui/material using default path imports, which is equivalent to R1. |
| `src/components/NewRunParametersV2.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/components/PipelinesDialog.tsx` | matches | judge | Migrated by rules | 0 | yes | The candidate moves the same four imports to @mui/material using path imports. This is equivalent to the reference's named import (R1/R2). |
| `src/components/PipelinesDialogV2.tsx` | matches | judge | Migrated by rules | 0 | yes | Candidate switches the same four imports to @mui/material path imports, which is equivalent to the reference's named imports in R1/R2. |
| `src/components/PlotCard.tsx` | matches | judge | Migrated by rules | 0 | yes | R1's import path changes are reproduced with equivalent default path imports instead of named imports. |
| `src/components/PrivateSharedSelector.tsx` | matches | judge | Migrated by rules | 0 | yes | R1: the candidate makes the same package change using default path imports, which is equivalent. |
| `src/components/ReduceGraphSwitch.tsx` | matches | judge | Migrated by rules | 0 | yes | Candidate changes the same imports to @mui/material path imports instead of a barrel import, which is equivalent. |
| `src/components/Router.tsx` | matches | judge | Migrated by rules | 0 | yes | Candidate switches all imports to @mui/material path imports, which is equivalent to R1/R2's barrel imports. |
| `src/components/SideNav.tsx` | matches | judge | Migrated by rules | 0 | yes | The candidate makes equivalent import path changes, using default imports instead of named ones, and adds the same size='large' on the IconButton as R3. |
| `src/components/SidePanel.tsx` | wrong | judge | Unmigrated | 1 |  | The candidate updates the imports (R1) but leaves out the wrapper div (R2). v5 Slide needs a ref-capable child, and Resizable is a class component that doesn't forward its ref to the DOM, so the transition breaks. |
| `src/components/Toolbar.tsx` | matches | judge | Migrated by rules | 0 | yes | The candidate updates the imports equivalently, using path imports instead of named imports (R1), and adds size='large' (R2). |
| `src/components/Trigger.tsx` | matches | judge | Migrated by rules | 0 | yes | The candidate switches the same four components to @mui/material using path imports, which is equivalent to the reference's named imports in R1/R2. |
| `src/components/TwoLevelDropdown.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/components/UploadPipelineDialog.tsx` | matches | judge | Migrated by rules | 0 | yes | R1's import path changes are reproduced with equivalent per-component @mui/material imports. |
| `src/components/graph/ArtifactNode.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/components/graph/ExecutionNode.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/components/graph/SubDagLayer.tsx` | matches | judge | Migrated by rules | 0 | yes | The candidate makes the same import changes as R1. It also deletes the license header comment, which is unrelated but does not break the file. |
| `src/components/graph/SubDagNode.tsx` | matches | deterministic | Migrated by rules | 0 | no | the same as the reference after normalising formatting |
| `src/components/navigators/PipelineVersionCard.tsx` | matches | judge | Unmigrated | 1 |  | Candidate uses equivalent path imports from @mui/material (R1) and adds the same variant='standard' props (R2). |
| `src/components/tabs/RuntimeNodeDetailsV2.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/components/tabs/StaticNodeDetailsV2.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/components/viewers/MetricsDropdown.tsx` | matches | judge | Unmigrated | 5 |  | The candidate replaces the import path with @mui/material/CircularProgress, which is equivalent to the reference's named import from @mui/material (R1/R2). |
| `src/components/viewers/MetricsVisualizations.tsx` | matches | judge | Migrated by rules | 0 | yes | Candidate updates the HelpIcon path and imports Tooltip from @mui/material/Tooltip in place, which is equivalent to R2+R3. |
| `src/components/viewers/PagedTable.tsx` | matches | judge | Migrated by rules | 0 | yes | For R1, the candidate imports the same components from @mui/material using path imports, which is equivalent to the reference's named imports. |
| `src/components/viewers/Tensorboard.tsx` | wrong | judge | Unmigrated | 1 |  | The candidate matches R1, R3 and R4 but does not change the event type in R2. In v5, Select's onChange passes a SelectChangeEvent, so the old React.ChangeEvent<{name?;value:unknown}> signature likely fails type checking. |
| `src/components/viewers/VisualizationCreator.tsx` | wrong | judge | Unmigrated | 11 |  | The candidate matches R1's import paths and R2's variants, but it leaves out R3. The old React.ChangeEvent<{name?; value: unknown}> handler type is incompatible with v5's Select onChange signature, so TypeScript compilation fails. |
| `src/icons/statusCached.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/index.tsx` | matches | judge | Migrated by rules | 0 | no | Candidate makes the same import change (R1) and the same StyledEngineProvider wrap (R2). Its extra DefaultTheme module augmentation is a harmless, codemod-standard type addition. |
| `src/lib/Buttons.ts` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/lib/WorkflowParser.ts` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/mlmd/Css.tsx` | other valid fix | judge | Migrated by rules | 0 | yes | The candidate updates the import (R1) and wraps the v4 theme in adaptV4Theme instead of rewriting it by hand (R2). adaptV4Theme converts overrides into styleOverrides and handles the $disabled/$focused/$active pseudo-class references, so the resulting theme is equivalent, though deprecated. |
| `src/mlmd/LineageActionBar.tsx` | matches | judge | Migrated by rules | 0 | yes | R1's import path changes are reproduced equivalently; the candidate uses a default Button import instead of a named one, which is equivalent. |
| `src/mlmd/LineageCard.tsx` | matches | deterministic | Migrated by rules | 0 | no | the same as the reference after normalising formatting |
| `src/mlmd/LineageCardColumn.tsx` | matches | judge | Migrated by rules | 0 | no | Candidate makes the same import change as R1. It also removes the license header, which does not affect behaviour. |
| `src/mlmd/LineageView.tsx` | matches | judge | Migrated by rules | 0 | no | The candidate makes the same R1 import change using an equivalent default-import path. |
| `src/pages/ArtifactDetails.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/pages/CompareV2.tsx` | matches | judge | Migrated by rules | 0 | yes | Candidate updates the CircularProgress import to @mui/material using an equivalent default-path import style. |
| `src/pages/ExecutionDetails.tsx` | matches | deterministic | Migrated by rules | 0 | no | the same as the reference after normalising formatting |
| `src/pages/ExperimentDetails.tsx` | matches | judge | Migrated by rules | 0 | yes | Candidate moves the same components and icon to @mui/material and @mui/icons-material using per-component default imports, which is equivalent to R1/R2's named barrel import. |
| `src/pages/ExperimentList.tsx` | matches | judge | Migrated by rules | 0 | yes | Candidate imports Tooltip from @mui/material/Tooltip, which is equivalent to the reference's named import in R1. |
| `src/pages/FrontendFeatures.tsx` | matches | judge | Migrated by rules | 0 | no | R1's package path change is reproduced equivalently with path imports from @mui/material. |
| `src/pages/NewExperiment.tsx` | matches | judge | Migrated by rules | 0 | yes | The candidate updates the Button and TextFieldProps imports to @mui/material, which is equivalent to R1 and R2; only the import style differs. |
| `src/pages/NewPipelineVersion.tsx` | matches | judge | Migrated by rules | 0 | yes | The candidate moves all the same imports to @mui/material using per-component default import paths, which is equivalent to the reference's R1/R2 named imports. |
| `src/pages/NewRun.tsx` | matches | judge | Migrated by rules | 0 | yes | Candidate switches all imports to @mui/material path imports, which is equivalent to R1/R2's named imports. |
| `src/pages/NewRunV2.tsx` | matches | deterministic | Unmigrated | 1 |  | the same as the reference after normalising formatting |
| `src/pages/Page.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/pages/PipelineDetailsV1.tsx` | matches | judge | Unmigrated | 13 |  | The candidate uses equivalent per-component @mui/material imports (R1, R2) and makes the same variant='standard' additions (R3). |
| `src/pages/PipelineList.tsx` | matches | judge | Migrated by rules | 0 | yes | The candidate changes the Tooltip import to @mui/material/Tooltip, which is equivalent to the reference's named import from @mui/material (R1/R2). |
| `src/pages/PipelineVersionList.tsx` | matches | judge | Migrated by rules | 0 | yes | The candidate imports Tooltip from @mui/material/Tooltip, which is equivalent to the reference's named import from @mui/material (R1/R2). |
| `src/pages/RecurringRunList.tsx` | matches | judge | Migrated by rules | 0 | yes | The candidate imports Tooltip from '@mui/material/Tooltip', which is equivalent to R1's named import from '@mui/material'. |
| `src/pages/RecurringRunsManager.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/pages/RunDetails.tsx` | matches | judge | Unmigrated | 45 |  | Candidate updates both imports to @mui paths; the default path import of CircularProgress is equivalent to the named import in R2. |
| `src/pages/RunList.tsx` | matches | judge | Migrated by rules | 0 | yes | R1: the candidate imports Tooltip via the default path import from @mui/material/Tooltip, which is equivalent to the reference's named import. |
| `src/pages/Status.tsx` | matches | judge | Migrated by rules | 0 | yes | The candidate makes the same import path changes as R1. It imports Tooltip by default import instead of a named import, which is equivalent. |
| `src/pages/StatusV2.tsx` | matches | judge | Migrated by rules | 0 | yes | The candidate makes the same import path changes as R1, using a default path import for Tooltip, which is equivalent. |
| `src/pages/functional_components/NewExperimentFC.tsx` | matches | judge | Migrated by rules | 0 | yes | Candidate replaces the Button import with @mui/material/Button, equivalent to R1+R2. |

## Reference changes set aside as out of scope

- `src/components/CustomTable.tsx`: R2: Blank line removed
- `src/components/CustomTable.tsx`: R3: Blank line removed
- `src/components/CustomTable.tsx`: R4: Blank line removed
- `src/components/viewers/VisualizationCreator.tsx`: R4: Remove a blank line

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
