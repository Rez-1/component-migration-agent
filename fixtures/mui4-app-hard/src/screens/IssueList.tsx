import { ChangeEvent, useState } from 'react';
import {
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TablePagination,
  TableRow,
  Typography,
} from '@material-ui/core';
import Skeleton from '@material-ui/lab/Skeleton';
import { makeStyles, Theme } from '@material-ui/core/styles';
import { Issue } from '../data/issues';

const useStyles = makeStyles((theme: Theme) => ({
  root: { padding: theme.spacing(2) },
  row: { cursor: 'pointer' },
}));

interface IssueListProps {
  issues: Issue[];
  loading?: boolean;
  onOpen?: (id: number) => void;
}

export function IssueList({ issues, loading = false, onOpen }: IssueListProps) {
  const classes = useStyles();
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(5);
  const rows = issues.slice(page * rowsPerPage, page * rowsPerPage + rowsPerPage);

  const handleRowsPerPage = (event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    setRowsPerPage(Number(event.target.value));
    setPage(0);
  };

  return (
    <section className={classes.root} aria-labelledby="issues-title">
      <Typography id="issues-title" variant="h5" component="h1">
        Issues
      </Typography>
      <TableContainer component={Paper}>
        <Table size="small" aria-labelledby="issues-title" aria-busy={loading}>
          <TableHead>
            <TableRow>
              <TableCell>#</TableCell>
              <TableCell>Title</TableCell>
              <TableCell>Priority</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {loading
              ? [0, 1, 2].map((n) => (
                  <TableRow key={n}>
                    <TableCell colSpan={3}>
                      <Skeleton variant="rect" height={20} />
                    </TableCell>
                  </TableRow>
                ))
              : rows.map((issue) => (
                  <TableRow
                    key={issue.id}
                    hover
                    className={classes.row}
                    onClick={() => onOpen?.(issue.id)}
                  >
                    <TableCell>{issue.id}</TableCell>
                    <TableCell>{issue.title}</TableCell>
                    <TableCell>{issue.priority}</TableCell>
                  </TableRow>
                ))}
          </TableBody>
        </Table>
      </TableContainer>
      <TablePagination
        component="div"
        count={issues.length}
        page={page}
        rowsPerPage={rowsPerPage}
        rowsPerPageOptions={[5, 10]}
        onPageChange={(_, next) => setPage(next)}
        onRowsPerPageChange={handleRowsPerPage}
        backIconButtonText="Previous issues"
        nextIconButtonText="Next issues"
      />
    </section>
  );
}
