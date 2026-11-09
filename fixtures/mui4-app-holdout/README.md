# warehouse-back-office

A small React 17 + TypeScript 4.9 back office for a warehouse, on Material UI v4 (`@material-ui/core` 4.12.4): seven screens under `src/screens/` (stock summary, orders, order details, inventory, product tags, returns, shipment tracking), the theme in `src/theme.ts`, the app shell in `src/App.tsx`, and Testing Library tests for each screen under `src/screens/__tests__/`.

## Running it

```bash
npm ci
npm run verify   # tsc --noEmit, eslint --max-warnings 0, jest
```
