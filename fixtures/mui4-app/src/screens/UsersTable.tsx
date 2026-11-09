import { useMemo, useState } from 'react';
import {
  Button,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Toolbar,
  Typography,
} from '@material-ui/core';
import { makeStyles, Theme } from '@material-ui/core/styles';
import { titleMinHeight } from './Dashboard';
import { USERS, User } from '../data/users';

const ROW_HEIGHT = 48;
const VISIBLE_ROWS = 8;

// Height of the header plus a fixed number of rows, so the page doesn't jump.
export const tableHeight = (theme: Theme, rows: number): number =>
  titleMinHeight(theme) + ROW_HEIGHT * rows;

const useStyles = makeStyles((theme: Theme) => ({
  toolbar: {
    padding: `${theme.spacing(1)}px ${theme.spacing(2)}px`,
    justifyContent: 'space-between',
  },
  table: {
    maxHeight: tableHeight(theme, VISIBLE_ROWS),
    overflowY: 'auto',
  },
}));

function toCsv(users: User[]): string {
  return ['name,email,role', ...users.map((u) => `${u.name},${u.email},${u.role}`)].join('\n');
}

export function UsersTable({ onExport }: { onExport?: (csv: string) => void }) {
  const classes = useStyles();
  const [filter, setFilter] = useState('');
  const visible = useMemo(
    () => USERS.filter((u) => u.name.toLowerCase().includes(filter.toLowerCase())),
    [filter],
  );

  return (
    <section aria-labelledby="users-title">
      <Toolbar className={classes.toolbar}>
        <Typography id="users-title" variant="h6" component="h1">
          Users
        </Typography>
        <TextField
          id="users-filter"
          label="Filter by name"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          size="small"
          variant="outlined"
        />
        <Button color="default" variant="outlined" onClick={() => onExport?.(toCsv(visible))}>
          Export CSV
        </Button>
      </Toolbar>
      <div className={classes.table}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Name</TableCell>
              <TableCell>Email</TableCell>
              <TableCell>Role</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {visible.map((user) => (
              <TableRow key={user.id}>
                <TableCell>{user.name}</TableCell>
                <TableCell>{user.email}</TableCell>
                <TableCell>{user.role}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        {visible.length === 0 && <Typography>No users match “{filter}”.</Typography>}
      </div>
    </section>
  );
}
