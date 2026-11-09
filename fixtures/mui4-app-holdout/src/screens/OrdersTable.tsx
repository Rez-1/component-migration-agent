import { useState } from 'react';
import {
  Chip,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableFooter,
  TableHead,
  TablePagination,
  TableRow,
  Typography,
} from '@material-ui/core';
import { Order, ORDERS, OrderStatus } from '../data/orders';

const STATUS_LABEL: Record<OrderStatus, string> = {
  new: 'New',
  picking: 'Picking',
  shipped: 'Shipped',
  cancelled: 'Cancelled',
};

const money = (value: number) => `€${value.toFixed(2)}`;

export function OrdersTable({
  orders = ORDERS,
  onOpen,
}: {
  orders?: Order[];
  onOpen?: (order: Order) => void;
}) {
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(5);
  const visible = orders.slice(page * rowsPerPage, page * rowsPerPage + rowsPerPage);

  return (
    <Paper component="section" aria-labelledby="orders-title">
      <Typography id="orders-title" variant="h6" component="h1" style={{ padding: 16 }}>
        Orders
      </Typography>
      <TableContainer>
        <Table size="small" aria-labelledby="orders-title">
          <TableHead>
            <TableRow>
              <TableCell>Order</TableCell>
              <TableCell>Customer</TableCell>
              <TableCell align="right">Items</TableCell>
              <TableCell align="right">Total</TableCell>
              <TableCell padding="default">Status</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {visible.map((order) => (
              <TableRow key={order.id} hover onClick={() => onOpen?.(order)}>
                <TableCell>{order.id}</TableCell>
                <TableCell>{order.customer}</TableCell>
                <TableCell align="right">{order.items}</TableCell>
                <TableCell align="right">{money(order.total)}</TableCell>
                <TableCell padding="default">
                  <Chip
                    size="small"
                    variant="default"
                    color={order.status === 'shipped' ? 'primary' : 'default'}
                    label={STATUS_LABEL[order.status]}
                  />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
          <TableFooter>
            <TableRow>
              <TablePagination
                count={orders.length}
                page={page}
                rowsPerPage={rowsPerPage}
                rowsPerPageOptions={[5, 10]}
                backIconButtonText="Previous page"
                nextIconButtonText="Next page"
                onPageChange={(_event, next) => setPage(next)}
                onRowsPerPageChange={(event) => {
                  setRowsPerPage(Number(event.target.value));
                  setPage(0);
                }}
              />
            </TableRow>
          </TableFooter>
        </Table>
      </TableContainer>
    </Paper>
  );
}
