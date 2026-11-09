import {
  Avatar,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Typography,
  withMobileDialog,
} from '@material-ui/core';
import { Order } from '../data/orders';

interface OrderDialogProps {
  order: Order;
  open: boolean;
  onClose: () => void;
  fullScreen?: boolean;
}

const initials = (name: string) =>
  name
    .split(' ')
    .map((part) => part[0])
    .join('')
    .slice(0, 2);

// Order details. Takes the whole screen on phones and small tablets.
function OrderDialogBase({ order, open, onClose, fullScreen }: OrderDialogProps) {
  return (
    <Dialog open={open} onClose={onClose} fullScreen={fullScreen} aria-labelledby="order-dialog-title">
      <DialogTitle id="order-dialog-title">Order {order.id}</DialogTitle>
      <DialogContent>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <Avatar variant="circle">{initials(order.customer)}</Avatar>
          <Typography>{order.customer}</Typography>
        </div>
        <Typography variant="body2" color="textSecondary">
          {order.items} {order.items === 1 ? 'item' : 'items'}, €{order.total.toFixed(2)}
        </Typography>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} color="primary">
          Close
        </Button>
      </DialogActions>
    </Dialog>
  );
}

export const OrderDialog = withMobileDialog<OrderDialogProps>()(OrderDialogBase);
