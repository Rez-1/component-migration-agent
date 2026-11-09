import { FocusEvent } from 'react';
import { InputBaseComponentProps } from '@material-ui/core';

// "90m", "1.5h" or "1h30" -> "1h 30m"; anything else is left as typed.
export function normaliseDuration(text: string): string {
  const trimmed = text.trim().toLowerCase();
  const hours = trimmed.match(/^(\d+(?:\.\d+)?)\s*h$/);
  const minutes = trimmed.match(/^(\d+)\s*m$/);
  const both = trimmed.match(/^(\d+)\s*h\s*(\d+)\s*m?$/);
  let total: number | null = null;
  if (hours) total = Math.round(Number(hours[1]) * 60);
  else if (minutes) total = Number(minutes[1]);
  else if (both) total = Number(both[1]) * 60 + Number(both[2]);
  if (total === null) return text;
  const h = Math.floor(total / 60);
  const m = total % 60;
  return [h ? `${h}h` : '', m ? `${m}m` : ''].filter(Boolean).join(' ') || '0m';
}

// An input that tidies the duration when the user leaves the field.
export function DurationInput(props: InputBaseComponentProps) {
  const { inputRef, onBlur, ...other } = props;
  return (
    <input
      {...other}
      ref={inputRef}
      onBlur={(event: FocusEvent<HTMLInputElement>) => {
        event.target.value = normaliseDuration(event.target.value);
        onBlur?.(event);
      }}
    />
  );
}
