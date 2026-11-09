import { createMuiTheme } from '@material-ui/core/styles';

// App-wide theme. Screens read spacing, palette and breakpoints from here.
export const theme = createMuiTheme({
  palette: {
    primary: { main: '#1f5fbf' },
    secondary: { main: '#c2410c' },
  },
  shape: { borderRadius: 6 },
  props: {
    MuiButtonBase: { disableRipple: true },
  },
  overrides: {
    // Product wants sentence-case buttons everywhere.
    MuiButton: {
      label: { textTransform: 'none' },
    },
  },
});
