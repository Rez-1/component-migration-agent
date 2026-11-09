import { useState } from 'react';
import {
  Box,
  Button,
  FormControlLabel,
  FormGroup,
  Paper,
  Switch,
  Typography,
} from '@material-ui/core';

export interface Preferences {
  emailDigest: boolean;
  productNews: boolean;
  darkMode: boolean;
}

const DEFAULTS: Preferences = { emailDigest: true, productNews: false, darkMode: false };

const LABELS: Record<keyof Preferences, string> = {
  emailDigest: 'Weekly email digest',
  productNews: 'Product news',
  darkMode: 'Dark mode (beta)',
};

export function Settings({ onSave }: { onSave?: (prefs: Preferences) => void }) {
  const [saved, setSaved] = useState<Preferences>(DEFAULTS);
  const [prefs, setPrefs] = useState<Preferences>(DEFAULTS);
  const dirty = (Object.keys(prefs) as (keyof Preferences)[]).some((k) => prefs[k] !== saved[k]);

  const toggle = (key: keyof Preferences) => (event: React.ChangeEvent<HTMLInputElement>) =>
    setPrefs({ ...prefs, [key]: event.target.checked });

  const save = () => {
    setSaved(prefs);
    onSave?.(prefs);
  };

  return (
    <Paper component="section" aria-labelledby="settings-title" style={{ padding: 24 }}>
      <Typography id="settings-title" variant="h6" component="h1">
        Settings
      </Typography>
      <FormGroup>
        {(Object.keys(LABELS) as (keyof Preferences)[]).map((key) => (
          <FormControlLabel
            key={key}
            control={<Switch checked={prefs[key]} onChange={toggle(key)} />}
            label={LABELS[key]}
          />
        ))}
      </FormGroup>
      <Box mt={2} display="flex" justifyContent="flex-end">
        <Button
          variant="contained"
          color={dirty ? 'primary' : 'default'}
          disabled={!dirty}
          onClick={save}
        >
          Save changes
        </Button>
      </Box>
      {!dirty && saved !== DEFAULTS && (
        <Typography role="status" variant="body2">
          Settings saved
        </Typography>
      )}
    </Paper>
  );
}
