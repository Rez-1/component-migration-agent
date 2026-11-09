import { Chip, TextField } from '@material-ui/core';
import { Autocomplete } from '@material-ui/lab';
import { Label, LABELS } from '../data/issues';

// What a screen reader hears (and the snackbar shows) after a change.
const ANNOUNCEMENTS: Record<string, (label: Label) => string> = {
  'select-option': (label) => `Added “${label.name}”`,
  'remove-option': (label) => `Removed “${label.name}”`,
};

interface LabelPickerProps {
  value: Label[];
  onChange: (labels: Label[]) => void;
  onAnnounce?: (message: string, label: Label) => void;
}

export function LabelPicker({ value, onChange, onAnnounce }: LabelPickerProps) {
  return (
    <Autocomplete
      multiple
      options={LABELS}
      value={value}
      getOptionLabel={(label) => label.name}
      getOptionSelected={(option, selected) => option.id === selected.id}
      filterSelectedOptions
      onChange={(_event, labels, reason, details) => {
        onChange(labels);
        const announce = ANNOUNCEMENTS[reason];
        if (announce && details) onAnnounce?.(announce(details.option), details.option);
      }}
      renderTags={(labels, getTagProps) =>
        labels.map((label, index) => (
          <Chip size="small" label={label.name} {...getTagProps({ index })} key={label.id} />
        ))
      }
      renderInput={(params) => <TextField {...params} label="Labels" variant="outlined" />}
    />
  );
}
