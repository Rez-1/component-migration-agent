// Shared test helpers. Imported only by test files.
import { ReactElement } from 'react';
import { render, RenderOptions } from '@testing-library/react';
import { AppProviders } from './App';

// Screens render inside the app shell (theme + CssBaseline), as in production.
export function renderScreen(ui: ReactElement, options?: RenderOptions) {
  return render(ui, { wrapper: AppProviders, ...options });
}
