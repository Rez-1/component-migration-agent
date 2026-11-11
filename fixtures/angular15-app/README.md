# triage-board

A small issue tracker for one team, on Angular 15 and Angular Material 15: an issue table with search, filters and paging, an issue page with labels and comments, a board, a team list and a settings page. It has no backend; the issues are sample data kept in memory (`src/app/data/`).

- `src/app/shared/`: the Material module list, and two shared components, `app-search-box` (a search field with a clear button) and `app-confirm-button` (a button that asks for a second click).
- `src/app/issues/`, `board/`, `team/`, `settings/`: the pages, each with its spec.
- `src/app/theme/_triage-theme.scss` and `src/styles.scss`: the palette, the type scale and the theme.

## Running it

Node 18 or 20.

```bash
npm ci
npx ng build                                          # production build to dist/triage-board
npx ng test --watch=false --browsers=ChromeHeadlessCI # Karma + Jasmine, headless Chrome
npx ng lint                                           # angular-eslint
npx ng serve                                          # http://localhost:4200
```

`ChromeHeadlessCI` (in `karma.conf.js`) is headless Chrome with `--no-sandbox`, for containers. Set `CHROME_BIN` if Chrome isn't found.
