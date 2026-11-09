import { FormEvent, useState } from 'react';
import { Button, FormControl, InputLabel, Select, TextField, Typography } from '@material-ui/core';
import { makeStyles, Theme } from '@material-ui/core/styles';

type Role = 'admin' | 'editor' | 'viewer';

const ROLE_LABELS: Record<Role, string> = {
  admin: 'Admin',
  editor: 'Editor',
  viewer: 'Viewer',
};

const useStyles = makeStyles((theme: Theme) => ({
  form: {
    display: 'grid',
    gap: theme.spacing(2),
    maxWidth: 360,
    padding: theme.spacing(2),
  },
}));

export interface ProfileValues {
  displayName: string;
  role: Role;
}

export function ProfileForm({ onSubmit }: { onSubmit?: (values: ProfileValues) => void }) {
  const classes = useStyles();
  const [displayName, setDisplayName] = useState('');
  const [role, setRole] = useState<Role>('viewer');
  const [message, setMessage] = useState<string | null>(null);

  const handleRoleChange = (event: React.ChangeEvent<{ name?: string; value: unknown }>) => {
    setRole(event.target.value as Role);
  };

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    onSubmit?.({ displayName, role });
    setMessage(`Saved ${displayName} (${ROLE_LABELS[role]})`);
  };

  return (
    <form className={classes.form} onSubmit={handleSubmit} aria-labelledby="profile-form-title">
      <Typography id="profile-form-title" variant="h6" component="h1">
        Edit profile
      </Typography>
      <TextField
        id="display-name"
        label="Display name"
        value={displayName}
        onChange={(e) => setDisplayName(e.target.value)}
        required
      />
      <FormControl variant="outlined">
        <InputLabel htmlFor="profile-role">Role</InputLabel>
        <Select
          native
          label="Role"
          value={role}
          onChange={handleRoleChange}
          inputProps={{ id: 'profile-role', name: 'role' }}
        >
          {(Object.keys(ROLE_LABELS) as Role[]).map((r) => (
            <option key={r} value={r}>
              {ROLE_LABELS[r]}
            </option>
          ))}
        </Select>
      </FormControl>
      <Button type="submit" variant="contained" color="primary" disabled={!displayName}>
        Save profile
      </Button>
      {message && <Typography role="status">{message}</Typography>}
    </form>
  );
}
