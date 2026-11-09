# mui4-tracker-app

A small issue tracker in React 17 + TypeScript 4.9 on Material UI v4 (`@material-ui/core` 4.12.4, `@material-ui/lab` for Autocomplete, Pagination, Skeleton and ToggleButton): six screens under `src/screens/` (Board, IssueList, IssueDetail, NewIssueDialog, Activity, Reports), shared components under `src/components/`, the theme in `src/theme.ts`, the app shell in `src/App.tsx`, and Testing Library tests for each screen under `src/screens/__tests__/`.

## Running it

```bash
npm ci
npm run verify   # tsc --noEmit, eslint --max-warnings 0, jest
```
