import { List, ListItem, ListItemText, Paper, Typography } from '@material-ui/core';
import { makeStyles, Theme } from '@material-ui/core/styles';
import { Skeleton } from '@material-ui/lab';
import { Product, PRODUCTS } from '../data/products';

const useStyles = makeStyles((theme: Theme) => ({
  header: {
    ...theme.mixins.gutters(),
    paddingTop: theme.spacing(2),
    paddingBottom: theme.spacing(1),
  },
  empty: {
    color: theme.palette.error.main,
  },
}));

export function Inventory({ products = PRODUCTS, loading = false }: { products?: Product[]; loading?: boolean }) {
  const classes = useStyles();
  return (
    <Paper component="section" aria-labelledby="inventory-title" aria-busy={loading}>
      <div className={classes.header}>
        <Typography id="inventory-title" variant="h6" component="h1">
          Inventory
        </Typography>
      </div>
      {loading ? (
        <div data-testid="inventory-loading">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} variant="rect" height={40} style={{ margin: 8 }} />
          ))}
        </div>
      ) : (
        <List dense>
          {products.map((p) => (
            <ListItem key={p.sku}>
              <ListItemText
                primary={`${p.name} (${p.sku})`}
                secondary={
                  p.onHand === 0 ? (
                    <span className={classes.empty}>Out of stock, bin {p.bin}</span>
                  ) : (
                    `${p.onHand} in bin ${p.bin}`
                  )
                }
              />
            </ListItem>
          ))}
        </List>
      )}
    </Paper>
  );
}
