# Reference score: opossum-ui, run 2026-11-18-221908-9ac (m8-agent-plain)

Scored against [https://github.com/opossum-tool/OpossumUI/pull/218](https://github.com/opossum-tool/OpossumUI/pull/218): 52 items (0 more out of scope).

| Verdict | Items |
|---|---|
| matches | 47 |
| other valid fix | 0 |
| wrong | 5 |
| untouched | 0 |
| out of scope | 0 |

**Silent misses** (wrong or untouched, and verify passes for the file): 5

| File | Verdict | By | Outcome | Final failures | Covered | Reason |
|---|---|---|---|---|---|---|
| `src/Frontend/Components/AggregatedAttributionsPanel/AggregatedAttributionsPanel.tsx` | matches | deterministic | Migrated by agent | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/AllAttributionsPanel/AllAttributionsPanel.tsx` | matches | deterministic | Migrated by agent | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/App/App.tsx` | matches | judge | Migrated by agent | 0 | yes | The candidate makes the same v5 changes as the reference: imports, module augmentation, styleOverrides and StyledEngineProvider. It keeps `const classes = useStyles()` instead of calling the hook inline, which is a harmless and arguably better difference. |
| `src/Frontend/Components/AttributionColumn/AttributionColumn.tsx` | matches | deterministic | Migrated by agent | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/AttributionColumn/AuditingSubPanel.tsx` | matches | deterministic | Migrated by agent | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/AttributionColumn/ButtonRow.tsx` | matches | deterministic | Migrated by agent | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/AttributionColumn/CopyrightSubPanel.tsx` | matches | deterministic | Migrated by agent | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/AttributionColumn/LicenseSubPanel.tsx` | matches | deterministic | Migrated by agent | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/AttributionColumn/PackageSubPanel.tsx` | matches | deterministic | Migrated by agent | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/AttributionColumn/shared-attribution-column-styles.ts` | matches | deterministic | Migrated by agent | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/AttributionDetailsViewer/AttributionDetailsViewer.tsx` | matches | deterministic | Migrated by agent | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/AttributionList/AttributionList.tsx` | matches | deterministic | Migrated by agent | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/AttributionView/AttributionView.tsx` | matches | deterministic | Migrated by agent | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/Button/Button.tsx` | matches | deterministic | Migrated by agent | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/Button/button-styles.ts` | wrong **(silent miss)** | judge | Migrated by agent | 0 | yes | The candidate matches R1 (the import change) but omits R2, the explicit black text colour on the light button that keeps its v4 appearance, so the look may differ. |
| `src/Frontend/Components/ButtonGroup/ButtonGroup.tsx` | matches | deterministic | Migrated by agent | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/Checkbox/Checkbox.tsx` | matches | deterministic | Migrated by agent | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/CommitInfoDisplay/CommitInfoDisplay.tsx` | matches | deterministic | Migrated by agent | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/ContextMenu/ContextMenu.tsx` | wrong **(silent miss)** | judge | Migrated by agent | 0 | yes | The candidate matches the import changes in R1 but omits the R2 padding on MuiListItemText, which the developers added to keep the v4 look. The menu item spacing will differ from the reference. |
| `src/Frontend/Components/ErrorBoundary/ErrorBoundary.tsx` | matches | judge | Migrated by agent | 0 | yes | The candidate makes the same import migration as R1, using @mui/styles and its subpath imports for createStyles and withStyles. R2 is an unrelated refactor and doesn't count against it. |
| `src/Frontend/Components/GoToLinkButton/GoToLinkButton.tsx` | matches | deterministic | Migrated by agent | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/HamburgerMenu/HamburgerMenu.tsx` | matches | deterministic | Migrated by agent | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/IconButton/IconButton.tsx` | matches | judge | Migrated by agent | 0 | yes | The candidate makes the same import changes as R1. The added `describeChild` prop on the Tooltip is an extra, harmless change: it only affects accessibility semantics and does not alter the visual result. |
| `src/Frontend/Components/Icons/Icons.tsx` | matches | judge | Migrated by agent | 0 | yes | The candidate makes the identical import changes as R1. The extra `describeChild` props on the tooltips are additive and do not break the migration. |
| `src/Frontend/Components/InputElements/AutoComplete.tsx` | matches | deterministic | Migrated by agent | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/InputElements/Dropdown.tsx` | matches | deterministic | Migrated by agent | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/InputElements/NumberBox.tsx` | matches | deterministic | Migrated by agent | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/InputElements/TextBox.tsx` | matches | deterministic | Migrated by agent | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/InputElements/shared.ts` | matches | deterministic | Migrated by agent | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/List/List.tsx` | matches | deterministic | Migrated by agent | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/ListCard/ListCard.tsx` | matches | deterministic | Migrated by agent | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/ManualPackagePanel/ManualPackagePanel.tsx` | matches | deterministic | Migrated by agent | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/NotificationPopup/NotificationPopup.tsx` | matches | deterministic | Migrated by agent | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/PackageCard/PackageCard.tsx` | matches | deterministic | Migrated by agent | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/PackagePanel/PackagePanel.tsx` | matches | deterministic | Migrated by agent | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/PathBar/PathBar.tsx` | matches | judge | Migrated by agent | 0 | yes | The candidate makes identical import changes to R1. It also adds `describeChild` to MuiTooltip, which only affects accessibility semantics (it keeps the title as the description, as v4 did), so it is harmless. |
| `src/Frontend/Components/ProgressBar/ProgressBar.tsx` | matches | judge | Migrated by agent | 0 | yes | The candidate makes identical import changes as R1. The extra `describeChild` prop on the Tooltip is a harmless addition that preserves v4 accessibility semantics, so it does not break anything. |
| `src/Frontend/Components/ProjectMetadataPopup/ProjectMetadataPopup.tsx` | matches | deterministic | Migrated by agent | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/ReplaceAttributionPopup/ReplaceAttributionPopup.tsx` | matches | deterministic | Migrated by agent | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/ReportTableHeader/ReportTableHeader.tsx` | matches | deterministic | Migrated by agent | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/ReportTableItem/ReportTableItem.tsx` | matches | deterministic | Migrated by agent | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/ReportView/ReportView.tsx` | matches | deterministic | Migrated by agent | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/ResourceBrowser/ResourceBrowser.tsx` | matches | deterministic | Migrated by agent | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/ResourceDetailsTabs/ResourceDetailsTabs.tsx` | wrong **(silent miss)** | judge | Migrated by agent | 0 | yes | The candidate matches R1 and R3 but omits the R2 tab styling (Mui-selected rule, colors and padding). Without it the tabs look different from the reference under v5 defaults. |
| `src/Frontend/Components/ResourceDetailsViewer/ResourceDetailsViewer.tsx` | matches | deterministic | Migrated by agent | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/ResourcePathPopup/ResourcePathPopup.tsx` | matches | deterministic | Migrated by agent | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/ResourcesList/ResourcesList.tsx` | matches | deterministic | Migrated by agent | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/SearchTextField/SearchTextField.tsx` | wrong **(silent miss)** | judge | Migrated by agent | 0 | yes | The candidate matches the import changes in R1 but leaves margin="dense" in place (R2). In v5 this no longer shrinks the input, so the field looks different from v4 and from the reference. |
| `src/Frontend/Components/StyledTreeItemLabel/StyledTreeItemLabel.tsx` | matches | deterministic | Migrated by agent | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/Table/Table.tsx` | matches | deterministic | Migrated by agent | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/ToggleButton/ToggleButton.tsx` | matches | deterministic | Migrated by agent | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/TopBar/TopBar.tsx` | wrong **(silent miss)** | judge | Migrated by agent | 0 | yes | The candidate matches the import changes in R1 and R2. It omits the R3 border on the selected toggle button, which is a v5-styling change that keeps the look consistent. |

## Reference changes set aside as out of scope

- `src/Frontend/Components/ErrorBoundary/ErrorBoundary.tsx`: R2: Swaps the order of connect and withStyles wrapping in the export; a refactor, not required by v5
- `src/Frontend/Components/TopBar/TopBar.tsx`: R4: Changes the aria-label text, probably for tests

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
