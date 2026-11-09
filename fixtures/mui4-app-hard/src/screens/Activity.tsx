import { FormEvent, useEffect, useRef, useState } from 'react';
import {
  Avatar,
  Button,
  List,
  ListItem,
  ListItemAvatar,
  ListItemText,
  RootRef,
  TextField,
  Typography,
} from '@material-ui/core';
import { makeStyles, Theme } from '@material-ui/core/styles';

const useStyles = makeStyles((theme: Theme) => ({
  root: { padding: theme.spacing(2), maxWidth: 560 },
  form: { display: 'flex', gap: theme.spacing(1), marginTop: theme.spacing(2) },
}));

interface Entry {
  id: number;
  who: string;
  initials: string;
  text: string;
}

const INITIAL: Entry[] = [
  { id: 1, who: 'Ada Lovelace', initials: 'AL', text: 'closed #103' },
  { id: 2, who: 'Linus Torvalds', initials: 'LT', text: 'commented on #108' },
];

export function Activity({ initial = INITIAL }: { initial?: Entry[] }) {
  const classes = useStyles();
  const [entries, setEntries] = useState(initial);
  const [draft, setDraft] = useState('');
  const listRef = useRef<HTMLElement>(null);
  const posted = useRef(false);

  // After posting, move focus to the new entry so keyboard and screen-reader
  // users land on what they just wrote.
  useEffect(() => {
    if (!posted.current) return;
    posted.current = false;
    const last = listRef.current?.lastElementChild as HTMLElement | null | undefined;
    last?.focus();
  }, [entries]);

  const post = (event: FormEvent) => {
    event.preventDefault();
    if (!draft.trim()) return;
    posted.current = true;
    setEntries((all) => [
      ...all,
      { id: all.length + 1, who: 'Grace Hopper', initials: 'GH', text: draft.trim() },
    ]);
    setDraft('');
  };

  return (
    <section className={classes.root} aria-labelledby="activity-title">
      <Typography id="activity-title" variant="h5" component="h1">
        Activity
      </Typography>
      <RootRef rootRef={listRef}>
        <List aria-label="Activity feed">
          {entries.map((entry) => (
            <ListItem key={entry.id} tabIndex={-1}>
              <ListItemAvatar>
                <Avatar>{entry.initials}</Avatar>
              </ListItemAvatar>
              <ListItemText primary={entry.text} secondary={entry.who} />
            </ListItem>
          ))}
        </List>
      </RootRef>
      <form className={classes.form} onSubmit={post}>
        <TextField
          id="activity-draft"
          label="Post an update"
          variant="outlined"
          size="small"
          fullWidth
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
        />
        <Button type="submit" variant="contained" color="primary">
          Post
        </Button>
      </form>
    </section>
  );
}
