import { useState } from 'react';
import {
  AppBar,
  Drawer,
  IconButton,
  List,
  ListItem,
  ListItemText,
  Tab,
  Tabs,
  Toolbar,
  Typography,
  useMediaQuery,
} from '@material-ui/core';
import { makeStyles, Theme, useTheme } from '@material-ui/core/styles';
import MenuIcon from '@material-ui/icons/Menu';

const useStyles = makeStyles((theme: Theme) => ({
  brand: {
    flexGrow: 1,
  },
  drawerList: {
    width: 240,
  },
  tabs: {
    marginLeft: theme.spacing(2),
  },
}));

export interface ResponsiveNavProps {
  pages: readonly string[];
  current: string;
  onNavigate: (page: string) => void;
}

// Phones and small tablets (below 960px wide) get a menu button and a drawer;
// wider screens get tabs.
export function ResponsiveNav({ pages, current, onNavigate }: ResponsiveNavProps) {
  const classes = useStyles();
  const theme = useTheme();
  const compact = useMediaQuery(theme.breakpoints.down('sm'));
  const [drawerOpen, setDrawerOpen] = useState(false);

  const go = (page: string) => {
    setDrawerOpen(false);
    onNavigate(page);
  };

  return (
    <AppBar position="static" component="nav" aria-label="Main">
      <Toolbar>
        {compact && (
          <IconButton edge="start" color="inherit" aria-label="Open menu" onClick={() => setDrawerOpen(true)}>
            <MenuIcon />
          </IconButton>
        )}
        <Typography variant="h6" className={classes.brand}>
          Workspace
        </Typography>
        {!compact && (
          <Tabs className={classes.tabs} value={current} onChange={(_, page: string) => go(page)}>
            {pages.map((page) => (
              <Tab key={page} value={page} label={page} />
            ))}
          </Tabs>
        )}
      </Toolbar>
      <Drawer open={drawerOpen} onClose={() => setDrawerOpen(false)}>
        <List className={classes.drawerList}>
          {pages.map((page) => (
            <ListItem button key={page} selected={page === current} onClick={() => go(page)}>
              <ListItemText primary={page} />
            </ListItem>
          ))}
        </List>
      </Drawer>
    </AppBar>
  );
}
