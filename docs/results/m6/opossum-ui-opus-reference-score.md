# Reference score: opossum-ui, run 2026-11-10-155441-5cb (m6-opus-low-v2)

Scored against [https://github.com/opossum-tool/OpossumUI/pull/218](https://github.com/opossum-tool/OpossumUI/pull/218): 52 items (0 more out of scope).

| Verdict | Items |
|---|---|
| matches | 46 |
| other valid fix | 1 |
| wrong | 5 |
| untouched | 0 |
| out of scope | 0 |

**Silent misses** (wrong or untouched, and verify passes for the file): 3

| File | Verdict | By | Outcome | Final failures | Covered | Reason |
|---|---|---|---|---|---|---|
| `src/Frontend/Components/AggregatedAttributionsPanel/AggregatedAttributionsPanel.tsx` | matches | deterministic | Handed off | 1 |  | the same as the reference after normalising formatting |
| `src/Frontend/Components/AllAttributionsPanel/AllAttributionsPanel.tsx` | matches | judge | Handed off | 1 |  | R1 is matched. The candidate imports from '@mui/material/Typography/Typography', which still resolves in v5 because the package ships Typography/Typography.js, so it is equivalent. |
| `src/Frontend/Components/App/App.tsx` | other valid fix | judge | Migrated by rules | 0 | yes | Instead of R3's manual conversion to components.styleOverrides, the candidate wraps the theme in adaptV4Theme, which produces the same result at runtime. It is deprecated but still a valid v5 approach. The other hunks match the reference. |
| `src/Frontend/Components/AttributionColumn/AttributionColumn.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/AttributionColumn/AuditingSubPanel.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/AttributionColumn/ButtonRow.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/AttributionColumn/CopyrightSubPanel.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/AttributionColumn/LicenseSubPanel.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/AttributionColumn/PackageSubPanel.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/AttributionColumn/shared-attribution-column-styles.ts` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/AttributionDetailsViewer/AttributionDetailsViewer.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/AttributionList/AttributionList.tsx` | matches | judge | Handed off | 1 |  | Candidate makes the same import changes in R1. '@mui/material/Typography/Typography' is a valid deep path in v5, so it is equivalent. |
| `src/Frontend/Components/AttributionView/AttributionView.tsx` | matches | deterministic | Handed off | 1 |  | the same as the reference after normalising formatting |
| `src/Frontend/Components/Button/Button.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/Button/button-styles.ts` | wrong **(silent miss)** | judge | Migrated by rules | 0 | yes | Candidate matches R1 but omits R2's added black text colour, so the light button shows v5's default primary-coloured text. |
| `src/Frontend/Components/ButtonGroup/ButtonGroup.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/Checkbox/Checkbox.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/CommitInfoDisplay/CommitInfoDisplay.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/ContextMenu/ContextMenu.tsx` | wrong **(silent miss)** | judge | Migrated by rules | 0 | yes | The candidate matches R1 but leaves out the v5-styling padding in R2, so the menu item text spacing differs from the reference. |
| `src/Frontend/Components/ErrorBoundary/ErrorBoundary.tsx` | matches | judge | Migrated by rules | 0 | yes | R1 is the only required change. The candidate makes the equivalent import move to @mui/styles using default-path imports. R2 is a refactor of the HOC order, not a v5 requirement. |
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
| `src/Frontend/Components/PackagePanel/PackagePanel.tsx` | matches | judge | Handed off | 1 |  | R1 is mirrored. The candidate's deep path '@mui/material/Typography/Typography' exists in v5 and resolves to the same component, so it is an equivalent import style. |
| `src/Frontend/Components/PathBar/PathBar.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/ProgressBar/ProgressBar.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/ProjectMetadataPopup/ProjectMetadataPopup.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/ReplaceAttributionPopup/ReplaceAttributionPopup.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/ReportTableHeader/ReportTableHeader.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/ReportTableItem/ReportTableItem.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/ReportView/ReportView.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/ResourceBrowser/ResourceBrowser.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/ResourceDetailsTabs/ResourceDetailsTabs.tsx` | wrong | judge | Handed off | 2 |  | The candidate only does the import changes (R1). It misses the v5 onChange event type change (R3) and the styling adjustments (R2). |
| `src/Frontend/Components/ResourceDetailsViewer/ResourceDetailsViewer.tsx` | matches | deterministic | Handed off | 1 |  | the same as the reference after normalising formatting |
| `src/Frontend/Components/ResourcePathPopup/ResourcePathPopup.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/ResourcesList/ResourcesList.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/SearchTextField/SearchTextField.tsx` | wrong **(silent miss)** | judge | Migrated by rules | 0 | yes | The candidate matches the imports (R1) but leaves out the v5-styling change in R2, size="small", so the field renders larger than in v4. |
| `src/Frontend/Components/StyledTreeItemLabel/StyledTreeItemLabel.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/Table/Table.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/ToggleButton/ToggleButton.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/Frontend/Components/TopBar/TopBar.tsx` | wrong | judge | Handed off | 1 |  | Candidate matches R1 and R2 but omits the v5-styling border added in R3 for the selected toggle button. |

## Reference changes set aside as out of scope

- `src/Frontend/Components/ErrorBoundary/ErrorBoundary.tsx`: R2: Reorder HOC composition of connect and withStyles
- `src/Frontend/Components/TopBar/TopBar.tsx`: R4: aria-label text change

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
