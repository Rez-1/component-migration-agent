// Shared test helpers. Imported only by test files.
import { ReactElement } from 'react';
import { render, RenderOptions } from '@testing-library/react';
import { AppProviders } from './App';

// Screens render inside the app shell (theme + CssBaseline), as in production.
export function renderScreen(ui: ReactElement, options?: RenderOptions) {
  return render(ui, { wrapper: AppProviders, ...options });
}

// Small presentational components render bare: they don't need the app shell.
export function renderComponent(ui: ReactElement, options?: RenderOptions) {
  return render(ui, options);
}

// jsdom has no matchMedia. This answers min-width / max-width queries for a
// fixed viewport width, which is all useMediaQuery needs.
export function mockViewportWidth(width: number) {
  const matches = (query: string) =>
    query.split(/\s+and\s+/).every((part) => {
      const m = part.match(/\((min|max)-width:\s*([\d.]+)px\)/);
      if (!m) return false;
      const value = Number(m[2]);
      return m[1] === 'min' ? width >= value : width <= value;
    });
  window.matchMedia = (query: string) =>
    ({
      matches: matches(query),
      media: query,
      onchange: null,
      addListener: () => undefined,
      removeListener: () => undefined,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      dispatchEvent: () => false,
    } as MediaQueryList);
}
