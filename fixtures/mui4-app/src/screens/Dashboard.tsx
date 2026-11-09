import { Grid, Paper, Typography } from '@material-ui/core';
import { fade, makeStyles, Theme } from '@material-ui/core/styles';

const useStyles = makeStyles((theme: Theme) => ({
  root: {
    padding: theme.spacing(2),
  },
  card: {
    padding: theme.spacing(2),
    marginTop: theme.spacing(1) * 3,
    backgroundColor: fade(theme.palette.primary.main, 0.06),
  },
  title: {
    marginBottom: theme.spacing(1),
    minHeight: titleMinHeight(theme),
  },
}));

// Shared with UsersTable so card titles and the table header line up.
export const titleMinHeight = (theme: Theme): number => theme.spacing(4) + 24;

export interface Kpi {
  label: string;
  value: string;
  trend: 'up' | 'down' | 'flat';
}

const KPIS: Kpi[] = [
  { label: 'Active users', value: '1,284', trend: 'up' },
  { label: 'Open tickets', value: '37', trend: 'down' },
  { label: 'Uptime', value: '99.95%', trend: 'flat' },
];

const TREND_TEXT: Record<Kpi['trend'], string> = {
  up: 'Up on last week',
  down: 'Down on last week',
  flat: 'Same as last week',
};

export function Dashboard({ kpis = KPIS }: { kpis?: Kpi[] }) {
  const classes = useStyles();
  return (
    <section className={classes.root} aria-labelledby="dashboard-title">
      <Grid container justify="space-between" alignItems="center">
        <Typography id="dashboard-title" variant="h4" component="h1">
          Dashboard
        </Typography>
        <Typography variant="body2" color="textSecondary">
          Last 7 days
        </Typography>
      </Grid>
      <Grid container spacing={2}>
        {kpis.map((kpi) => (
          <Grid item xs={12} md={4} key={kpi.label}>
            <Paper className={classes.card} component="article" aria-label={kpi.label}>
              <Typography variant="subtitle2" component="h2" className={classes.title}>
                {kpi.label}
              </Typography>
              <Typography variant="h5">{kpi.value}</Typography>
              <Typography variant="caption">{TREND_TEXT[kpi.trend]}</Typography>
            </Paper>
          </Grid>
        ))}
      </Grid>
    </section>
  );
}
