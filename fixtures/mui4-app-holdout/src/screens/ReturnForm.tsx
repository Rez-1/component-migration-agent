import { FormEvent, useState } from 'react';
import { Button, Checkbox, FormControlLabel, Paper, TextField, Typography } from '@material-ui/core';
import { makeStyles, Theme } from '@material-ui/core/styles';

const useStyles = makeStyles((theme: Theme) => {
  // Damaged returns go to the inspection bench first; the button says so in amber.
  const inspection = theme.palette.augmentColor({ main: '#b45309' });
  return {
    root: { padding: theme.spacing(3), maxWidth: 480 },
    inspect: {
      backgroundColor: inspection.main,
      color: inspection.contrastText,
      '&:hover': { backgroundColor: inspection.dark },
    },
  };
});

export interface ReturnRequest {
  orderId: string;
  reason: string;
  damaged: boolean;
}

export function ReturnForm({ onSubmit }: { onSubmit?: (request: ReturnRequest) => void }) {
  const classes = useStyles();
  const [orderId, setOrderId] = useState('');
  const [reason, setReason] = useState('');
  const [damaged, setDamaged] = useState(false);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    onSubmit?.({ orderId: orderId.trim(), reason: reason.trim(), damaged });
  };

  return (
    <Paper component="form" className={classes.root} onSubmit={submit} aria-labelledby="return-title">
      <Typography id="return-title" variant="h6" component="h1">
        Log a return
      </Typography>
      <TextField
        id="return-order"
        label="Order number"
        value={orderId}
        onChange={(e) => setOrderId(e.target.value)}
        fullWidth
        margin="normal"
        required
      />
      <TextField
        id="return-reason"
        label="Reason"
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        fullWidth
        margin="normal"
        multiline
        rowsMax={6}
      />
      <FormControlLabel
        control={<Checkbox checked={damaged} onChange={(e) => setDamaged(e.target.checked)} />}
        label="Item arrived damaged"
      />
      <div>
        <Button
          type="submit"
          variant="contained"
          color={damaged ? undefined : 'primary'}
          className={damaged ? classes.inspect : undefined}
        >
          {damaged ? 'Send to inspection' : 'Log return'}
        </Button>
      </div>
    </Paper>
  );
}
