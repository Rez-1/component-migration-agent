# Reference score: opossum-ui, run 2026-11-16-120326-056 (m6-opus-low-v4)

Scored against [https://github.com/opossum-tool/OpossumUI/pull/218](https://github.com/opossum-tool/OpossumUI/pull/218): 52 items (0 more out of scope).

| Verdict | Items |
|---|---|
| matches | 43 |
| other valid fix | 4 |
| wrong | 5 |
| untouched | 0 |
| out of scope | 0 |

**Silent misses** (wrong or untouched, and verify passes for the file): 3

| File | Verdict | By | Outcome | Final failures | Covered | Reason |
|---|---|---|---|---|---|---|
| `src/Frontend/Components/AggregatedAttributionsPanel/AggregatedAttributionsPanel.tsx` | matches | deterministic | Handed off | 1 |  | the same as the reference after normalising formatting |
| `src/Frontend/Components/AllAttributionsPanel/AllAttributionsPanel.tsx` | other valid fix | judge | Handed off | 1 |  | The candidate makes the same import changes, except it imports Typography from '@mui/material/Typography/Typography' instead of '@mui/material/Typography'. That deep path resolves in v5 (the folder contains Typography.js), so it is equivalent, though less standard. |
| `src/Frontend/Components/App/App.tsx` | other valid fix | judge | Migrated by rules | 0 | yes | The candidate matches the imports, module augmentation and StyledEngineProvider wrapper. For the theme it uses adaptV4Theme instead of rewriting to components.styleOverrides, which is a valid, officially supported v5 migration path with the same result. It keeps the classes variable, which is fine because that part of the reference is an unrelated refactor. |
| `src/Frontend/Components/AttributionColumn/AttributionColumn.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/AttributionColumn/AuditingSubPanel.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/AttributionColumn/ButtonRow.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/AttributionColumn/CopyrightSubPanel.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/AttributionColumn/LicenseSubPanel.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/AttributionColumn/PackageSubPanel.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/AttributionColumn/shared-attribution-column-styles.ts` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/AttributionDetailsViewer/AttributionDetailsViewer.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/AttributionList/AttributionList.tsx` | other valid fix | judge | Handed off | 1 |  | The candidate matches the reference on makeStyles. It imports Typography from '@mui/material/Typography/Typography' instead of '@mui/material/Typography'. That deep path resolves to the same component in v5, so behavior is the same, though it is a less canonical import. |
| `src/Frontend/Components/AttributionView/AttributionView.tsx` | matches | deterministic | Handed off | 1 |  | the same as the reference after normalising formatting |
| `src/Frontend/Components/Button/Button.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/Button/button-styles.ts` | wrong **(silent miss)** | judge | Migrated by rules | 0 | yes | The candidate matches the import change in R1 but omits the explicit `color: OpossumColors.black` added in R2, which preserves the v4 look for the light button. |
| `src/Frontend/Components/ButtonGroup/ButtonGroup.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/Checkbox/Checkbox.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/CommitInfoDisplay/CommitInfoDisplay.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/ContextMenu/ContextMenu.tsx` | wrong **(silent miss)** | judge | Migrated by rules | 0 | yes | The candidate matches R1 imports but omits the R2 padding compensation (sx pl: 2) on ListItemText, so the icon/text spacing would differ from the reference. |
| `src/Frontend/Components/ErrorBoundary/ErrorBoundary.tsx` | matches | judge | Migrated by rules | 0 | yes | The candidate makes the R1 import migration to @mui/styles, using the equivalent default-import paths for createStyles and withStyles. R2 is an unrelated reordering, so the candidate does not need to reproduce it. |
| `src/Frontend/Components/GoToLinkButton/GoToLinkButton.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/HamburgerMenu/HamburgerMenu.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/IconButton/IconButton.tsx` | matches | deterministic | Handed off | 1 |  | the same as the reference after normalising formatting |
| `src/Frontend/Components/Icons/Icons.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/InputElements/AutoComplete.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/InputElements/Dropdown.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/InputElements/NumberBox.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/InputElements/TextBox.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/InputElements/shared.ts` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/List/List.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/ListCard/ListCard.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/ManualPackagePanel/ManualPackagePanel.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/NotificationPopup/NotificationPopup.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/PackageCard/PackageCard.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/PackagePanel/PackagePanel.tsx` | other valid fix | judge | Handed off | 1 |  | The makeStyles import matches. The candidate imports Typography from '@mui/material/Typography/Typography', a deep path that resolves to the same component in v5, but it is not the documented path. It works, though it is less clean than the reference. |
| `src/Frontend/Components/PathBar/PathBar.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/ProgressBar/ProgressBar.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/ProjectMetadataPopup/ProjectMetadataPopup.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/ReplaceAttributionPopup/ReplaceAttributionPopup.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/ReportTableHeader/ReportTableHeader.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/ReportTableItem/ReportTableItem.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/ReportView/ReportView.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/ResourceBrowser/ResourceBrowser.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/ResourceDetailsTabs/ResourceDetailsTabs.tsx` | wrong | judge | Handed off | 2 |  | The candidate only changes the imports (R1). It omits the v5 Tabs onChange type change (R3) and the Mui-selected and background styling that preserves the v4 look (R2). |
| `src/Frontend/Components/ResourceDetailsViewer/ResourceDetailsViewer.tsx` | matches | deterministic | Handed off | 1 |  | the same as the reference after normalising formatting |
| `src/Frontend/Components/ResourcePathPopup/ResourcePathPopup.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/ResourcesList/ResourcesList.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/SearchTextField/SearchTextField.tsx` | wrong **(silent miss)** | judge | Migrated by rules | 0 | yes | The candidate matches the import changes in R1 but leaves margin="dense" on the TextField (R2). In v5 that no longer shrinks the outlined input, so the compact look from v4 is lost. |
| `src/Frontend/Components/StyledTreeItemLabel/StyledTreeItemLabel.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/Table/Table.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/ToggleButton/ToggleButton.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/TopBar/TopBar.tsx` | wrong | judge | Handed off | 1 |  | The candidate matches the import changes in R1 and R2. It omits the R3 styling addition for the selected toggle button border, so the selected state looks different from the reference. |

## Reference changes set aside as out of scope

- `src/Frontend/Components/ErrorBoundary/ErrorBoundary.tsx`: R2: Reorders connect and withStyles composition in the export; not required by v5
- `src/Frontend/Components/TopBar/TopBar.tsx`: R4: Change the icon aria-label text, likely a test or accessibility tweak

## Test files the reference changed (expected hand-offs)

- `src/Frontend/Components/AggregatedAttributionsPanel/__tests__/AggregatedAttributionsPanel.test.tsx`
- `src/Frontend/Components/AllAttributionsPanel/__tests__/AllAttributionsPanel.test.tsx`
- `src/Frontend/Components/AttributionColumn/__tests__/attribution-column-helpers.test.ts`
- `src/Frontend/Components/AttributionList/__tests__/AttributionList.test.tsx`
- `src/Frontend/Components/IconButton/__tests__/IconButton.test.tsx`
- `src/Frontend/Components/ManualAttributionList/__tests__/ManualAttributionList.test.tsx`
- `src/Frontend/test-helpers/attribution-column-test-helpers.ts`
- `src/Frontend/test-helpers/context-menu-test-helpers.ts`
- `src/Frontend/test-helpers/package-panel-helpers.ts`

## Other files the reference changed (not scored)

- `package.json`
- `src/Frontend/Components/AttributionColumn/attribution-column-helpers.ts`
- `yarn.lock`

Judge: 0 new calls, $0.00.
