import { useState } from 'react';
import { List, ListItem, ListItemText, Typography } from '@material-ui/core';
import { Pagination, ToggleButton, ToggleButtonGroup } from '@material-ui/lab';
import { makeStyles, Theme } from '@material-ui/core/styles';
import { Issue } from '../data/issues';
import { TEAM } from '../data/people';
import { RangeSlider } from '../components/RangeSlider';

const useStyles = makeStyles((theme: Theme) => ({
  root: { padding: theme.spacing(2), maxWidth: 560 },
  controls: { margin: theme.spacing(2, 0) },
}));

type Grouping = 'priority' | 'assignee';
const PAGE_SIZE = 3;

function groupIssues(issues: Issue[], by: Grouping): [string, number][] {
  const counts = new Map<string, number>();
  for (const issue of issues) {
    const key =
      by === 'priority'
        ? issue.priority
        : TEAM.find((p) => p.id === issue.assignee)?.name ?? 'Unassigned';
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return Array.from(counts.entries()).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
}

export function Reports({ issues }: { issues: Issue[] }) {
  const classes = useStyles();
  const [age, setAge] = useState<[number, number]>([0, 30]);
  const [grouping, setGrouping] = useState<Grouping>('priority');
  const [page, setPage] = useState(1);

  const inRange = issues.filter((i) => i.daysOpen >= age[0] && i.daysOpen <= age[1]);
  const groups = groupIssues(inRange, grouping);
  const pages = Math.max(1, Math.ceil(groups.length / PAGE_SIZE));
  const shown = groups.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  return (
    <section className={classes.root} aria-labelledby="reports-title">
      <Typography id="reports-title" variant="h5" component="h1">
        Reports
      </Typography>
      <div className={classes.controls}>
        <RangeSlider
          id="age-label"
          label="Days open"
          min={0}
          max={30}
          value={age}
          unit=" days"
          onChange={(_, value) => {
            setAge(value as [number, number]);
            setPage(1);
          }}
        />
        <ToggleButtonGroup
          exclusive
          size="small"
          value={grouping}
          onChange={(_, value: Grouping | null) => {
            if (value) {
              setGrouping(value);
              setPage(1);
            }
          }}
          aria-label="Group by"
        >
          <ToggleButton value="priority">By priority</ToggleButton>
          <ToggleButton value="assignee">By assignee</ToggleButton>
        </ToggleButtonGroup>
      </div>
      <Typography>{inRange.length} issues</Typography>
      <List aria-label="Groups">
        {shown.map(([name, count]) => (
          <ListItem key={name}>
            <ListItemText primary={name} secondary={`${count} issues`} />
          </ListItem>
        ))}
      </List>
      <Pagination count={pages} page={page} onChange={(_, p) => setPage(p)} shape="round" />
    </section>
  );
}
