import { RefObject } from 'react';

// Dialog props that move focus to a field once the dialog has finished opening
// (the field isn't focusable while the dialog is still fading in).
export function focusOnOpen(field: RefObject<HTMLElement>) {
  return {
    onEntered: () => field.current?.focus(),
  };
}
