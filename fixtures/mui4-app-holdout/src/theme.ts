import { createMuiTheme } from '@material-ui/core/styles';

// Back-office theme: compact type, teal brand colour.
export const theme = createMuiTheme({
  palette: {
    type: 'light',
    primary: { main: '#0f766e' },
    secondary: { main: '#7c3aed' },
  },
  typography: { fontSize: 13 },
  shape: { borderRadius: 4 },
  props: {
    MuiButtonBase: { disableRipple: true },
  },
});
