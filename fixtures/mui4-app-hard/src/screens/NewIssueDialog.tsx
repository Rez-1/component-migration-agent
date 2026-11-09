import { useRef, useState } from 'react';
import {
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  TextField,
} from '@material-ui/core';
import { Autocomplete } from '@material-ui/lab';
import { makeStyles, Theme } from '@material-ui/core/styles';
import { CURRENT_USER, Person, TEAM } from '../data/people';
import { personPickerProps } from '../components/personPicker';
import { DurationInput } from '../components/DurationInput';

const useStyles = makeStyles((theme: Theme) => ({
  field: { marginBottom: theme.spacing(2) },
}));

export interface NewIssue {
  title: string;
  assignee: string | null;
  reviewer: string | null;
  estimate: string;
}

export function NewIssueDialog({ onCreate }: { onCreate?: (issue: NewIssue) => void }) {
  const classes = useStyles();
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState('');
  const [assignee, setAssignee] = useState<Person | null>(CURRENT_USER);
  const [reviewer, setReviewer] = useState<Person | null>(null);
  const titleRef = useRef<HTMLInputElement>(null);
  const estimateRef = useRef<HTMLInputElement>(null);

  const create = () => {
    onCreate?.({
      title: title.trim(),
      assignee: assignee?.id ?? null,
      reviewer: reviewer?.id ?? null,
      estimate: estimateRef.current?.value ?? '',
    });
    setOpen(false);
  };

  return (
    <>
      <Button variant="contained" color="primary" onClick={() => setOpen(true)}>
        New issue
      </Button>
      <Dialog
        open={open}
        onClose={() => setOpen(false)}
        onEntered={() => titleRef.current?.focus()}
        aria-labelledby="new-issue-title"
        fullWidth
      >
        <DialogTitle id="new-issue-title">New issue</DialogTitle>
        <DialogContent>
          <TextField
            id="issue-title-field"
            className={classes.field}
            label="Title"
            fullWidth
            variant="outlined"
            inputRef={titleRef}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
          <Autocomplete
            {...personPickerProps}
            className={classes.field}
            options={TEAM}
            value={assignee}
            onChange={(_, person) => setAssignee(person)}
            renderInput={(params) => <TextField {...params} label="Assignee" variant="outlined" />}
          />
          <Autocomplete
            {...personPickerProps}
            className={classes.field}
            options={TEAM}
            value={reviewer}
            onChange={(_, person) => setReviewer(person)}
            renderInput={(params) => <TextField {...params} label="Reviewer" variant="outlined" />}
          />
          <TextField
            id="issue-estimate"
            label="Estimate"
            placeholder="e.g. 90m or 1.5h"
            fullWidth
            variant="outlined"
            inputRef={estimateRef}
            InputProps={{ inputComponent: DurationInput }}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>Cancel</Button>
          <Button color="primary" disabled={!title.trim()} onClick={create}>
            Create
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
