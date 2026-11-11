# Reference score: bcgov-wps, run 2026-11-11-090925-2b2 (m6-baseline)

Scored against [https://github.com/bcgov/wps/pull/1933](https://github.com/bcgov/wps/pull/1933): 123 items (2 more out of scope).

| Verdict | Items |
|---|---|
| matches | 103 |
| other valid fix | 4 |
| wrong | 15 |
| untouched | 1 |
| out of scope | 2 |

**Silent misses** (wrong or untouched, and verify passes for the file): 13

| File | Verdict | By | Outcome | Final failures | Covered | Reason |
|---|---|---|---|---|---|---|
| `.storybook/preview.js` | out of scope | judge |  | 0 |  | R1 deletes the file entirely, which is a refactor/relocation rather than a v5-driven change within this file. |
| `src/app/App.tsx` | other valid fix | judge | Migrated by rules | 0 | no | R1: the candidate has the same imports, augmentation and StyledEngineProvider wrapper, but leaves CssBaseline outside the provider. CssBaseline is global styles and does not depend on the theme, so the result looks and behaves essentially the same. |
| `src/app/theme.ts` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/components/Button.tsx` | matches | judge | Migrated by rules | 0 | no | The candidate makes the same import-path changes as R1. R2 and the extra theme import are a refactor; makeStyles from @mui/styles with a theme callback still works when a ThemeProvider is present. |
| `src/components/Contact.tsx` | matches | judge | Migrated by rules | 0 | no | The candidate makes the same import change as R1. The fontSize tweak in R1 is not tied to any v5 default change, so it is unrelated. |
| `src/components/Container.tsx` | matches | deterministic | Migrated by rules | 0 | no | the same as the reference after normalising formatting |
| `src/components/DatePicker.tsx` | untouched | judge | Unmigrated | 6 |  | The reference removes the file that uses @material-ui/pickers (R1), a v5-required change. The candidate left it unchanged. |
| `src/components/ErrorBoundary.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/components/ErrorMessage.tsx` | matches | judge | Migrated by rules | 0 | no | The candidate makes the v5-required import change from R1. Importing the theme directly (R1/R2) avoids needing a ThemeProvider/DefaultTheme typing, but using the callback theme with @mui/styles is still valid as long as a ThemeProvider exists, so this is a refactor choice. |
| `src/components/FilterColumnsModal.tsx` | matches | deterministic | Migrated by rules | 0 | no | the same as the reference after normalising formatting |
| `src/components/FireTable.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/components/GeneralHeader.tsx` | matches | deterministic | Migrated by rules | 0 | no | the same as the reference after normalising formatting |
| `src/components/Grid.tsx` | matches | deterministic | Migrated by rules | 0 | no | the same as the reference after normalising formatting |
| `src/components/HFICell.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/components/HeaderImage.tsx` | matches | deterministic | Migrated by rules | 0 | no | the same as the reference after normalising formatting |
| `src/components/PageTitle.tsx` | wrong **(silent miss)** | judge | Migrated by rules | 0 | no | The candidate moves the import to @mui/styles/makeStyles but keeps the theme callback parameter. Without a ThemeProvider from @mui/styles the theme is empty, which R1 avoids by importing the app theme. Unless a provider supplies it, theme accesses would break. |
| `src/components/PercentileHeader.tsx` | wrong **(silent miss)** | judge | Migrated by rules | 0 | no | R1 swaps the makeStyles theme callback for an imported theme. In v5, @mui/styles makeStyles gets no default theme unless a ThemeProvider supplies it, so theme.palette may be undefined. The candidate only changes the import and keeps the callback theme, which risks a runtime break. |
| `src/components/Slider.tsx` | matches | deterministic | Migrated by rules | 0 | no | the same as the reference after normalising formatting |
| `src/components/StickyCell.tsx` | matches | judge | Unmigrated | 1 |  | Candidate makes the same import changes as R1. Using the imported theme in R2 is a project-specific workaround for @mui/styles needing a ThemeProvider, which we can't judge as required without more context. |
| `src/components/WPSDatePicker.tsx` | out of scope | judge |  | 0 |  | The only reference hunk, R1, creates a new component file, which is a new feature rather than a v4-to-v5 change. The empty candidate is therefore acceptable. |
| `src/components/dateRangePicker/Day.tsx` | matches | judge | Migrated by rules | 0 | yes | Candidate updates imports to @mui/material and @mui/styles (R1) and adds size="large" (R2). Keeping the theme param in makeStyles is valid, assuming a ThemeProvider is in place. |
| `src/components/dateRangePicker/Header.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/components/dateRangePicker/Menu.tsx` | other valid fix | judge | Unmigrated | 2 |  | The candidate makes the same import path changes as R1. It keeps the makeStyles theme callback instead of importing the app theme, which works as long as a ThemeProvider supplies the theme, and that is the standard codemod approach. |
| `src/components/dateRangePicker/Month.tsx` | matches | deterministic | Unmigrated | 3 |  | the same as the reference after normalising formatting |
| `src/features/cHaines/pages/CHainesPage.tsx` | matches | deterministic | Migrated by rules | 0 | no | the same as the reference after normalising formatting |
| `src/features/fba/components/FBAMap.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/features/fba/components/FormalFBATable.tsx` | matches | deterministic | Migrated by rules | 0 | no | the same as the reference after normalising formatting |
| `src/features/fba/pages/FireBehaviourAdvisoryPage.tsx` | matches | judge | Migrated by rules | 0 | no | The candidate makes the same import change as R1. The variant="standard" it adds to FormControl is the codemod's way of keeping the v4 default and is harmless. The DatePicker swap is a project-specific refactor, not part of the v5 migration. |
| `src/features/fbaCalculator/components/CriticalHoursCell.tsx` | matches | deterministic | Migrated by rules | 0 | no | the same as the reference after normalising formatting |
| `src/features/fbaCalculator/components/CrownFractionBurnedCell.tsx` | matches | deterministic | Migrated by rules | 0 | no | the same as the reference after normalising formatting |
| `src/features/fbaCalculator/components/ErrorAlert.tsx` | matches | judge | Migrated by rules | 0 | no | R1's import migrations are reproduced. The candidate keeps the theme argument on makeStyles instead of importing the app theme. That is valid as long as a ThemeProvider supplies the theme, and it makes the same required v5 changes. |
| `src/features/fbaCalculator/components/FBAProgressRow.tsx` | wrong **(silent miss)** | judge | Migrated by rules | 0 | yes | Candidate matches R1 except it leaves literal '(' and ')' text nodes inside StyledEngineProvider (a codemod artifact). Inside a table body these render as stray text, which produces invalid DOM and visible characters. |
| `src/features/fbaCalculator/components/FBATable.tsx` | wrong | judge | Unmigrated | 2 |  | The candidate keeps color="default" on the two Buttons (R7, R8), which v5 no longer supports. It does match the import changes in R1. |
| `src/features/fbaCalculator/components/FBATableHead.tsx` | matches | deterministic | Migrated by rules | 0 | no | the same as the reference after normalising formatting |
| `src/features/fbaCalculator/components/FBATableInstructions.tsx` | matches | deterministic | Migrated by rules | 0 | no | the same as the reference after normalising formatting |
| `src/features/fbaCalculator/components/FireCenterDropdown.tsx` | matches | judge | Migrated by rules | 0 | no | The candidate imports both components from @mui/material, using separate import lines, which is equivalent to R1. |
| `src/features/fbaCalculator/components/FixedDecimalNumberCell.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/features/fbaCalculator/components/FuelTypeCell.tsx` | matches | judge | Migrated by rules | 0 | no | The candidate makes the same import moves, using separate import lines, which is equivalent (R1). It also makes the same prop rename (R2). |
| `src/features/fbaCalculator/components/GrassCureCell.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/features/fbaCalculator/components/LoadingIndicatorCell.tsx` | matches | judge | Migrated by rules | 0 | yes | The candidate imports both components from @mui/material using two separate import lines, which is equivalent to R1. |
| `src/features/fbaCalculator/components/SelectionCell.tsx` | matches | deterministic | Unmigrated | 3 |  | the same as the reference after normalising formatting |
| `src/features/fbaCalculator/components/StatusCell.tsx` | matches | deterministic | Migrated by rules | 0 | no | the same as the reference after normalising formatting |
| `src/features/fbaCalculator/components/TableHeader.tsx` | matches | deterministic | Migrated by rules | 0 | no | the same as the reference after normalising formatting |
| `src/features/fbaCalculator/components/TextDisplayCell.tsx` | matches | deterministic | Migrated by rules | 0 | no | the same as the reference after normalising formatting |
| `src/features/fbaCalculator/components/WeatherStationCell.tsx` | matches | judge | Migrated by rules | 0 | no | The candidate makes the same import changes (split across two lines, which is equivalent) and the same prop rename as R1 and R2. |
| `src/features/fbaCalculator/components/WindSpeedCell.tsx` | wrong **(silent miss)** | judge | Migrated by rules | 0 | yes | The candidate leaves out the fontSize 0.875rem compensation in R2. In R3 it also adds literal parentheses that would render as stray text. |
| `src/features/fbaCalculator/pages/FireBehaviourCalculatorPage.tsx` | matches | deterministic | Migrated by rules | 0 | no | the same as the reference after normalising formatting |
| `src/features/fireWeather/components/AccuracyColorLegend.tsx` | wrong **(silent miss)** | judge | Migrated by rules | 0 | no | Candidate matches R1 but omits the R2 fontSize compensation, so the title would render at a different size than in v4. |
| `src/features/fireWeather/components/AccuracyVariablePicker.tsx` | wrong **(silent miss)** | judge | Migrated by rules | 0 | no | The candidate matches R1 and R3 but leaves out R2's styling fix that keeps the InputLabel white in v5, where emotion's specificity would override the JSS colour. The label would look different. |
| `src/features/fireWeather/components/ExpandableContainer.tsx` | matches | deterministic | Migrated by rules | 0 | no | the same as the reference after normalising formatting |
| `src/features/fireWeather/components/NetworkErrorMessages.tsx` | matches | deterministic | Migrated by rules | 0 | no | the same as the reference after normalising formatting |
| `src/features/fireWeather/components/SidePanel.tsx` | matches | deterministic | Migrated by rules | 0 | no | the same as the reference after normalising formatting |
| `src/features/fireWeather/components/StationAccuracyForDate.tsx` | wrong **(silent miss)** | judge | Migrated by rules | 0 | no | The candidate matches R1 but leaves out the R2 fontSize styling, which keeps the text at its v4 size. |
| `src/features/fireWeather/components/TimeOfInterestPicker.tsx` | matches | deterministic | Migrated by rules | 0 | no | the same as the reference after normalising formatting |
| `src/features/fireWeather/components/WxDataDisplays.tsx` | matches | deterministic | Migrated by rules | 0 | no | the same as the reference after normalising formatting |
| `src/features/fireWeather/components/WxDataForm.tsx` | matches | deterministic | Migrated by rules | 0 | no | the same as the reference after normalising formatting |
| `src/features/fireWeather/components/WxStationDropdown.tsx` | matches | deterministic | Migrated by rules | 0 | no | the same as the reference after normalising formatting |
| `src/features/fireWeather/components/graphs/WxDataGraph.tsx` | wrong **(silent miss)** | judge | Migrated by rules | 0 | no | Candidate matches R1 but omits the R2/R3 SelectChangeEvent type change. v5's Select onChange signature requires that change, so the old React.ChangeEvent handler type would likely fail type-checking. |
| `src/features/fireWeather/components/graphs/WxDataGraphToggles.tsx` | wrong | judge | Unmigrated | 1 |  | Candidate omits R2: the handler type React.ChangeEvent<{name?,value:unknown}> is incompatible with v5 Select's onChange (SelectChangeEvent), causing a type error. |
| `src/features/fireWeather/components/maps/LayerSwitch.tsx` | matches | judge | Migrated by rules | 0 | no | The candidate makes the same import changes as R1. It also adds variant="standard" to FormControl, which keeps the v4 default and has no visible effect on a fieldset, so it is harmless. |
| `src/features/fireWeather/components/tables/ComparisonTableRow.tsx` | matches | deterministic | Migrated by rules | 0 | no | the same as the reference after normalising formatting |
| `src/features/fireWeather/components/tables/NoonForecastTable.tsx` | matches | deterministic | Migrated by rules | 0 | no | the same as the reference after normalising formatting |
| `src/features/fireWeather/components/tables/SortableTableByDatetime.tsx` | matches | deterministic | Migrated by rules | 0 | no | the same as the reference after normalising formatting |
| `src/features/fireWeather/components/tables/StationComparisonTable.tsx` | matches | deterministic | Migrated by rules | 0 | no | the same as the reference after normalising formatting |
| `src/features/fireWeather/pages/MoreCastPage.tsx` | matches | deterministic | Migrated by rules | 0 | no | the same as the reference after normalising formatting |
| `src/features/fwiCalculator/components/BasicFWIGrid.tsx` | matches | deterministic | Migrated by rules | 0 | no | the same as the reference after normalising formatting |
| `src/features/fwiCalculator/components/BasicFWIInput.tsx` | matches | deterministic | Migrated by rules | 0 | no | the same as the reference after normalising formatting |
| `src/features/fwiCalculator/components/BasicFWIOutput.tsx` | matches | judge | Migrated by rules | 0 | no | The candidate moves the same imports to @mui/material. It imports Skeleton in a separate statement, which is equivalent to R1. |
| `src/features/fwiCalculator/components/FWIDatePicker.tsx` | matches | judge | Migrated by rules | 0 | no | For R1 the candidate makes equivalent import path changes. R2 is an unrelated refactor. The added size="large" on IconButton is the codemod's way of keeping v4 sizing, so it is harmless. |
| `src/features/fwiCalculator/components/FWIDateRange.tsx` | matches | deterministic | Migrated by rules | 0 | no | the same as the reference after normalising formatting |
| `src/features/fwiCalculator/components/FWINumberCell.tsx` | matches | deterministic | Migrated by rules | 0 | no | the same as the reference after normalising formatting |
| `src/features/fwiCalculator/components/FWIStationCell.tsx` | matches | judge | Migrated by rules | 0 | no | The candidate makes the same import change, only split across two import lines (R1), and the same prop rename (R2). |
| `src/features/fwiCalculator/components/FWIStationSelect.tsx` | matches | judge | Migrated by rules | 0 | no | The candidate makes both changes. Its import is split across two lines but is equivalent to R1, and its prop rename is identical to R2. |
| `src/features/fwiCalculator/components/FWIToggle.tsx` | matches | judge | Migrated by rules | 0 | no | The candidate makes the same import changes as R1. R2 and R3 are an unrelated refactor. |
| `src/features/fwiCalculator/components/MultiDayFWITable.tsx` | other valid fix | judge | Migrated by rules | 0 | no | The candidate makes the same import changes as R1. It also adds size="large" to the IconButtons, which is the codemod's way of keeping v4's default size, so the buttons look the same as in v4. |
| `src/features/fwiCalculator/components/MultiFWITableCell.tsx` | matches | deterministic | Migrated by rules | 0 | no | the same as the reference after normalising formatting |
| `src/features/fwiCalculator/components/YesterdayIndices.tsx` | matches | judge | Migrated by rules | 0 | no | The candidate imports the same components from @mui/material using two import lines instead of one, which is equivalent to R1. |
| `src/features/fwiCalculator/pages/FWICalculatorPage.tsx` | matches | deterministic | Migrated by rules | 0 | no | the same as the reference after normalising formatting |
| `src/features/hfiCalculator/components/AboutDataModal.tsx` | matches | deterministic | Migrated by rules | 0 | no | the same as the reference after normalising formatting |
| `src/features/hfiCalculator/components/BaseStationAttributeCells.tsx` | matches | deterministic | Migrated by rules | 0 | no | the same as the reference after normalising formatting |
| `src/features/hfiCalculator/components/CalculatedCell.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/features/hfiCalculator/components/CalculatedPlanningAreaCells.tsx` | matches | deterministic | Migrated by rules | 0 | no | the same as the reference after normalising formatting |
| `src/features/hfiCalculator/components/DailyViewTable.tsx` | matches | deterministic | Migrated by rules | 0 | no | the same as the reference after normalising formatting |
| `src/features/hfiCalculator/components/DayHeaders.tsx` | matches | deterministic | Unmigrated | 1 |  | the same as the reference after normalising formatting |
| `src/features/hfiCalculator/components/DayIndexHeaders.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/features/hfiCalculator/components/DownloadPDFButton.tsx` | matches | deterministic | Migrated by rules | 0 | no | the same as the reference after normalising formatting |
| `src/features/hfiCalculator/components/EmptyFireCentre.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/features/hfiCalculator/components/EmptyStaticCells.tsx` | matches | deterministic | Migrated by rules | 0 | no | the same as the reference after normalising formatting |
| `src/features/hfiCalculator/components/ErrorIconWithTooltip.tsx` | wrong **(silent miss)** | judge | Migrated by rules | 0 | yes | In R2 the candidate leaves literal '(' and ')' text inside the StyledEngineProvider JSX (a known codemod artifact). These render as visible parentheses around the icon, so the result looks different from the reference. |
| `src/features/hfiCalculator/components/FireCentreCell.tsx` | matches | deterministic | Migrated by rules | 0 | no | the same as the reference after normalising formatting |
| `src/features/hfiCalculator/components/FireCentreDropdown.tsx` | wrong **(silent miss)** | judge | Migrated by rules | 0 | no | The candidate matches R1 imports and R3 but omits R2, the endAdornment positioning adjustment made to keep the v4 look. |
| `src/features/hfiCalculator/components/FireStartsCell.tsx` | matches | deterministic | Migrated by rules | 0 | no | the same as the reference after normalising formatting |
| `src/features/hfiCalculator/components/FireStartsDropdown.tsx` | matches | judge | Unmigrated | 2 |  | The candidate makes the same import moves (split across two import lines, which is equivalent) and the same prop rename as R1 and R2. |
| `src/features/hfiCalculator/components/GrassCureCell.tsx` | matches | deterministic | Unmigrated | 1 |  | the same as the reference after normalising formatting |
| `src/features/hfiCalculator/components/HFIErrorAlert.tsx` | matches | judge | Unmigrated | 1 |  | Candidate makes equivalent import migrations (Alert from @mui/material, makeStyles/createStyles from @mui/styles, icons path) while keeping the theme param, which is a valid equivalent of R1. |
| `src/features/hfiCalculator/components/HFILoadingDataView.tsx` | matches | deterministic | Unmigrated | 2 |  | the same as the reference after normalising formatting |
| `src/features/hfiCalculator/components/HFIPageSubHeader.tsx` | wrong **(silent miss)** | judge | Migrated by rules | 0 | no | Candidate updates imports but keeps makeStyles(theme => ...) relying on the theme argument; in v5 without a @mui/styles ThemeProvider the theme is empty, so theme.palette access breaks, which R1 avoids by importing the app theme. The added variant="standard" on FormControl is harmless. |
| `src/features/hfiCalculator/components/HFISuccessAlert.tsx` | matches | judge | Migrated by rules | 0 | no | For R1 the candidate makes the same import changes, only using two separate @mui/material import lines, which is equivalent. |
| `src/features/hfiCalculator/components/HeaderRowCell.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/features/hfiCalculator/components/HighestDailyFIGCell.tsx` | matches | deterministic | Migrated by rules | 0 | no | the same as the reference after normalising formatting |
| `src/features/hfiCalculator/components/IntensityGroupCell.tsx` | matches | deterministic | Unmigrated | 1 |  | the same as the reference after normalising formatting |
| `src/features/hfiCalculator/components/LastUpdatedHeader.tsx` | matches | deterministic | Migrated by rules | 0 | no | the same as the reference after normalising formatting |
| `src/features/hfiCalculator/components/LiveChangesAlert.tsx` | matches | judge | Migrated by rules | 0 | no | R1's import migrations are reproduced equivalently; keeping the Theme type from @mui/material/styles is fine. |
| `src/features/hfiCalculator/components/MeanIntensityGroupRollup.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/features/hfiCalculator/components/MeanPrepLevelCell.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/features/hfiCalculator/components/PrepDateRangeSelector.tsx` | wrong **(silent miss)** | judge | Migrated by rules | 0 | no | The candidate keeps the v4 MuiOutlinedInput root override with $notchedOutline and does not add WebkitTextFillColor. In v5 the disabled input text then renders greyed out instead of white, unlike R1's restyled theme. |
| `src/features/hfiCalculator/components/PrepLevelCell.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/features/hfiCalculator/components/RequiredDataCell.tsx` | matches | deterministic | Migrated by rules | 0 | no | the same as the reference after normalising formatting |
| `src/features/hfiCalculator/components/StaticCells.tsx` | matches | deterministic | Migrated by rules | 0 | no | the same as the reference after normalising formatting |
| `src/features/hfiCalculator/components/StationDataHeaderCells.tsx` | matches | deterministic | Migrated by rules | 0 | no | the same as the reference after normalising formatting |
| `src/features/hfiCalculator/components/StatusCell.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/features/hfiCalculator/components/ViewSwitcherToggles.tsx` | wrong **(silent miss)** | judge | Migrated by rules | 0 | no | The candidate only updates the imports (R1). It leaves the .MuiToggleButton-label selector in place, but v5 no longer renders that element, so the lineHeight style is lost, and the height styling from R2 is also missing. |
| `src/features/hfiCalculator/components/WeeklyROSCell.tsx` | matches | deterministic | Migrated by rules | 0 | yes | the same as the reference after normalising formatting |
| `src/features/hfiCalculator/components/WeeklyViewTable.tsx` | matches | deterministic | Migrated by rules | 0 | no | the same as the reference after normalising formatting |
| `src/features/hfiCalculator/pages/HfiCalculatorPage.tsx` | matches | judge | Migrated by rules | 0 | no | The candidate makes R1's import migration. Keeping the imported theme works equivalently, and variant="standard" on FormControl keeps the v4 default. |
| `src/features/map/Map.tsx` | matches | deterministic | Migrated by rules | 0 | no | the same as the reference after normalising formatting |
| `src/features/percentileCalculator/components/PercentileActionButtons.tsx` | matches | deterministic | Migrated by rules | 0 | no | the same as the reference after normalising formatting |
| `src/features/percentileCalculator/components/PercentileCalcDocumentation.tsx` | matches | deterministic | Migrated by rules | 0 | no | the same as the reference after normalising formatting |
| `src/features/percentileCalculator/components/PercentileMeanResultTable.tsx` | other valid fix | judge | Migrated by rules | 0 | no | The candidate makes the same import changes as R1 but keeps the theme callback. The theme-import change is a typing/DefaultTheme workaround, and with a ThemeProvider in place the callback works identically. |
| `src/features/percentileCalculator/components/PercentileResults.tsx` | matches | deterministic | Migrated by rules | 0 | no | the same as the reference after normalising formatting |
| `src/features/percentileCalculator/components/PercentileStationResultTable.tsx` | matches | deterministic | Migrated by rules | 0 | no | the same as the reference after normalising formatting |
| `src/features/percentileCalculator/components/PercentileTextfield.tsx` | matches | deterministic | Migrated by rules | 0 | no | the same as the reference after normalising formatting |
| `src/features/percentileCalculator/components/TimeRangeSlider.tsx` | matches | judge | Unmigrated | 2 |  | The candidate makes the same v5-required import changes as R1. Replacing the custom Slider wrapper with a width class is a refactor, and the wrapper is presumably migrated in its own file. |
| `src/features/percentileCalculator/components/WxStationDropdown.tsx` | matches | judge | Migrated by rules | 0 | no | Candidate makes identical import changes as R1. Its added underline="hover" keeps the v4 default Link underline behaviour, so it is a harmless v5-preserving addition. |
| `src/features/percentileCalculator/pages/PercentileCalculatorPageWithDisclaimer.tsx` | matches | judge | Migrated by rules | 0 | no | Candidate makes the same import changes as R1. R2 is a width change unrelated to v5. |

## Reference changes set aside as out of scope

- `.storybook/preview.js`: R1: Deletes the whole storybook preview file (likely moved/renamed to another file, e.g. preview.jsx), not a v5 requirement per se
- `src/components/Button.tsx`: R2: makeStyles callback stops taking theme as an argument and uses the imported theme instead; a refactor or workaround, not required by v5.
- `src/components/ErrorMessage.tsx`: R2: Uses the imported theme instead of the makeStyles callback theme argument.
- `src/components/StickyCell.tsx`: R2: Use imported theme instead of makeStyles theme callback argument (workaround for missing ThemeProvider theme in @mui/styles)
- `src/components/WPSDatePicker.tsx`: R1: Adds a brand-new WPSDatePicker component wrapping the @mui/lab DatePicker with a Luxon adapter; this is a new file and a new feature, not a migration of existing v4 code.
- `src/features/fba/pages/FireBehaviourAdvisoryPage.tsx`: R2: Replaces the pstFormatter import with the new WPSDatePicker component.
- `src/features/fba/pages/FireBehaviourAdvisoryPage.tsx`: R3: Date state changes from a string to a DateTime to suit the new picker component.
- `src/features/fba/pages/FireBehaviourAdvisoryPage.tsx`: R4: Swaps DatePicker for the project's WPSDatePicker component.
- `src/features/fbaCalculator/components/FBATable.tsx`: R2: Remove old DatePicker import (date picker rewrite)
- `src/features/fbaCalculator/components/FBATable.tsx`: R3: Swap pstFormatter import for WPSDatePicker
- `src/features/fbaCalculator/components/FBATable.tsx`: R4: dateOfInterest state becomes DateTime
- `src/features/fbaCalculator/components/FBATable.tsx`: R5: updateDate takes DateTime, uses isEqual
- `src/features/fbaCalculator/components/FBATable.tsx`: R6: Use WPSDatePicker component
- `src/features/fwiCalculator/components/FWIDatePicker.tsx`: R2: Switches to the new WPSDatePicker component with a DateTime-based API, a refactor.
- `src/features/fwiCalculator/components/FWIToggle.tsx`: R2: makeStyles callback changed to a plain object
- `src/features/fwiCalculator/components/FWIToggle.tsx`: R3: Closing of the makeStyles object refactor
- `src/features/hfiCalculator/pages/HfiCalculatorPage.tsx`: R2: makeStyles now uses the theme callback argument instead of the imported theme.
- `src/features/percentileCalculator/components/TimeRangeSlider.tsx`: R2: Applies the slider width class as part of swapping to the MUI Slider.
- `src/features/percentileCalculator/pages/PercentileCalculatorPageWithDisclaimer.tsx`: R2: Card maxWidth changed 600->800, a design change not caused by v5

## Test files the reference changed (expected hand-offs)

- `cypress/integration/percentile-calculator-page.spec.ts`
- `src/components/datePicker.test.tsx`
- `src/components/fireTable.test.tsx`
- `src/components/hfiCell.test.tsx`
- `src/components/stickyCell.test.tsx`
- `src/features/fbaCalculator/components/fbaProgressRow.test.tsx`
- `src/features/fbaCalculator/components/loadingIndicatorCell.test.tsx`
- `src/features/fbaCalculator/components/selectionCell.test.tsx`
- `src/features/hfiCalculator/components/DayHeaders.test.tsx`
- `src/features/hfiCalculator/components/dailyHFICell.test.tsx`
- `src/features/hfiCalculator/components/dayIndexHeaders.test.tsx`
- `src/features/hfiCalculator/components/emptyFireCentre.test.tsx`
- `src/features/hfiCalculator/components/fireStartsDropdown.test.tsx`
- `src/features/hfiCalculator/components/grassCureCell.test.tsx`
- `src/features/hfiCalculator/components/headerRowCell.test.tsx`
- `src/features/hfiCalculator/components/intensityGroupCell.test.tsx`
- `src/features/hfiCalculator/components/meanIntensityGroupRollup.test.tsx`
- `src/features/hfiCalculator/components/meanPrepLevelCell.test.tsx`
- `src/features/hfiCalculator/components/prepLevelCell.test.tsx`
- `src/features/hfiCalculator/components/statusCell.test.tsx`
- `src/features/hfiCalculator/components/weeklyRosCell.test.tsx`

## Other files the reference changed (not scored)

- `.storybook/main.js`
- `package.json`
- `src/features/fbaCalculator/slices/fbaCalculatorSlice.ts`
- `yarn.lock`

Judge: 0 new calls, $0.00.
