import { useRef, useState } from 'react';
import {
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Paper,
  Snackbar,
  TextField,
  Typography,
} from '@material-ui/core';
import { makeStyles, Theme } from '@material-ui/core/styles';
import { Issue, Label } from '../data/issues';
import { LabelPicker } from '../components/LabelPicker';
import { focusOnOpen } from '../components/dialogFocus';

const useStyles = makeStyles((theme: Theme) => ({
  root: { padding: theme.spacing(2), margin: theme.spacing(2), maxWidth: 560 },
  section: { marginTop: theme.spacing(2) },
}));

interface IssueDetailProps {
  issue: Issue;
  onComment?: (text: string) => void;
}

export function IssueDetail({ issue, onComment }: IssueDetailProps) {
  const classes = useStyles();
  const [labels, setLabels] = useState<Label[]>(issue.labels);
  const [notice, setNotice] = useState<{ message: string; undo: Label[] } | null>(null);
  const [commenting, setCommenting] = useState(false);
  const [comment, setComment] = useState('');
  const commentRef = useRef<HTMLTextAreaElement>(null);

  const postComment = () => {
    onComment?.(comment);
    setComment('');
    setCommenting(false);
  };

  return (
    <Paper className={classes.root} component="article" aria-labelledby="issue-title">
      <Typography id="issue-title" variant="h5" component="h1">
        #{issue.id} {issue.title}
      </Typography>
      <div className={classes.section}>
        <LabelPicker
          value={labels}
          onChange={setLabels}
          onAnnounce={(message) => setNotice({ message, undo: labels })}
        />
      </div>
      <div className={classes.section}>
        <Button variant="outlined" onClick={() => setCommenting(true)}>
          Comment
        </Button>
      </div>
      <Dialog
        open={commenting}
        onClose={() => setCommenting(false)}
        aria-labelledby="comment-title"
        fullWidth
        {...focusOnOpen(commentRef)}
      >
        <DialogTitle id="comment-title">Comment on #{issue.id}</DialogTitle>
        <DialogContent>
          <TextField
            id="comment-text"
            label="Comment"
            multiline
            rows={4}
            fullWidth
            variant="outlined"
            inputRef={commentRef}
            value={comment}
            onChange={(e) => setComment(e.target.value)}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCommenting(false)}>Cancel</Button>
          <Button color="primary" disabled={!comment.trim()} onClick={postComment}>
            Post
          </Button>
        </DialogActions>
      </Dialog>
      <Snackbar
        open={notice !== null}
        message={notice?.message}
        autoHideDuration={6000}
        onClose={() => setNotice(null)}
        action={
          <Button
            color="secondary"
            size="small"
            onClick={() => {
              if (notice) setLabels(notice.undo);
              setNotice(null);
            }}
          >
            Undo
          </Button>
        }
      />
    </Paper>
  );
}
