import { createMuiTheme } from '@material-ui/core/styles';
import { Status } from './data/issues';

export const statusColors: Record<Status, string> = {
  open: '#2563eb',
  'in-progress': '#d97706',
  done: '#16a34a',
};

export const theme = createMuiTheme({
  palette: {
    primary: { main: '#4338ca' },
    secondary: { main: '#db2777' },
  },
  shape: { borderRadius: 4 },
  props: {
    MuiTabs: { indicatorColor: 'primary', textColor: 'primary' },
  },
  overrides: {
    MuiTab: {
      root: {
        textTransform: 'none',
        '&$selected': { fontWeight: 700 },
      },
    },
  },
});
