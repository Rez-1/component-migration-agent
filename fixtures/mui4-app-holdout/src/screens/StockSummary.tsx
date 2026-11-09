import { CircularProgress, Grid, Paper, Typography } from '@material-ui/core';
import { makeStyles, Theme } from '@material-ui/core/styles';

const useStyles = makeStyles((theme: Theme) => ({
  tile: {
    padding: theme.spacing(2),
    display: 'flex',
    alignItems: 'center',
    gap: theme.spacing(2),
    backgroundColor: theme.palette.type === 'dark' ? theme.palette.grey[800] : theme.palette.grey[100],
  },
  value: {
    lineHeight: 1.2,
    marginTop: theme.spacing(1) / 2,
  },
}));

export interface StockFigures {
  unitsOnHand: number;
  openOrders: number;
  capacityUsed: number; // percent of bin space in use
}

const FIGURES: StockFigures = { unitsOnHand: 213, openOrders: 9, capacityUsed: 72 };

export function StockSummary({ figures = FIGURES }: { figures?: StockFigures }) {
  const classes = useStyles();
  const tiles = [
    { label: 'Units on hand', value: figures.unitsOnHand.toLocaleString('en-GB') },
    { label: 'Open orders', value: String(figures.openOrders) },
  ];
  return (
    <section aria-labelledby="stock-title">
      <Typography id="stock-title" variant="h5" component="h1" gutterBottom>
        Stock summary
      </Typography>
      <Grid container spacing={2}>
        {tiles.map((tile) => (
          <Grid item xs={12} sm={4} key={tile.label}>
            <Paper className={classes.tile} component="article" aria-label={tile.label}>
              <div>
                <Typography variant="overline">{tile.label}</Typography>
                <Typography variant="h5" className={classes.value}>
                  {tile.value}
                </Typography>
              </div>
            </Paper>
          </Grid>
        ))}
        <Grid item xs={12} sm={4}>
          <Paper className={classes.tile} component="article" aria-label="Capacity">
            <CircularProgress
              variant="static"
              value={figures.capacityUsed}
              aria-label="Bin capacity used"
            />
            <Typography variant="h5" className={classes.value}>
              {figures.capacityUsed}%
            </Typography>
          </Paper>
        </Grid>
      </Grid>
    </section>
  );
}
