import { useState } from 'react';
import { Card, CardActionArea, CardContent, Tab, Tabs, Typography } from '@material-ui/core';
import { makeStyles, Theme } from '@material-ui/core/styles';
import { Issue, Status } from '../data/issues';
import { statusColors } from '../theme';
import { StatusChip } from '../components/StatusChip';

const useStyles = makeStyles((theme: Theme) => ({
  root: { padding: theme.spacing(2) },
  cards: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))',
    gap: theme.spacing(2),
    marginTop: theme.spacing(2),
  },
  title: { marginBottom: theme.spacing(1) },
}));

type Filter = 'all' | Status;

const FILTERS: { value: Filter; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'open', label: 'Open' },
  { value: 'in-progress', label: 'In progress' },
  { value: 'done', label: 'Done' },
];

export function Board({ issues, onOpen }: { issues: Issue[]; onOpen?: (id: number) => void }) {
  const classes = useStyles();
  const [filter, setFilter] = useState<Filter>('all');
  const shown = filter === 'all' ? issues : issues.filter((i) => i.status === filter);

  return (
    <section className={classes.root} aria-labelledby="board-title">
      <Typography id="board-title" variant="h5" component="h1">
        Board
      </Typography>
      <Tabs value={filter} onChange={(_, value: Filter) => setFilter(value)} aria-label="Status">
        {FILTERS.map((f) => (
          <Tab
            key={f.value}
            value={f.value}
            label={`${f.label} (${
              f.value === 'all' ? issues.length : issues.filter((i) => i.status === f.value).length
            })`}
          />
        ))}
      </Tabs>
      <div className={classes.cards}>
        {shown.map((issue) => (
          <Card key={issue.id} variant="outlined">
            <CardActionArea onClick={() => onOpen?.(issue.id)}>
              <CardContent>
                <Typography className={classes.title} component="h2" variant="subtitle1">
                  #{issue.id} {issue.title}
                </Typography>
                <StatusChip status={issue.status} color={statusColors[issue.status]} />
              </CardContent>
            </CardActionArea>
          </Card>
        ))}
      </div>
    </section>
  );
}
