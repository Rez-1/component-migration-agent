import { useState } from 'react';
import {
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  TextField,
} from '@material-ui/core';

const CONFIRM_WORD = 'DELETE';

export function AccountDialog({ onDelete }: { onDelete?: () => void }) {
  const [open, setOpen] = useState(false);
  const [confirmation, setConfirmation] = useState('');

  const handleClose = () => {
    setOpen(false);
    setConfirmation('');
  };

  const handleDelete = () => {
    onDelete?.();
    handleClose();
  };

  return (
    <>
      <Button color="secondary" variant="outlined" onClick={() => setOpen(true)}>
        Delete account
      </Button>
      {/* A half-typed confirmation must not be lost to a stray click outside. */}
      <Dialog open={open} onClose={handleClose} disableBackdropClick aria-labelledby="delete-title">
        <DialogTitle id="delete-title">Delete your account?</DialogTitle>
        <DialogContent>
          <DialogContentText>
            This removes your profile and all your data. Type {CONFIRM_WORD} to confirm.
          </DialogContentText>
          <TextField
            autoFocus
            fullWidth
            variant="outlined"
            id="delete-confirmation"
            label="Confirmation"
            value={confirmation}
            onChange={(e) => setConfirmation(e.target.value)}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={handleClose}>Cancel</Button>
          <Button
            color="secondary"
            variant="contained"
            disabled={confirmation !== CONFIRM_WORD}
            onClick={handleDelete}
          >
            Delete
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
