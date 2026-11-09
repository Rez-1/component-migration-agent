export type OrderStatus = 'new' | 'picking' | 'shipped' | 'cancelled';

export interface Order {
  id: string;
  customer: string;
  items: number;
  total: number;
  status: OrderStatus;
}

const CUSTOMERS = ['Brightside Cafe', 'Nordic Tools', 'Kiosk 24', 'Green Leaf', 'Atlas Print', 'Harbour Books'];
const STATUSES: OrderStatus[] = ['new', 'picking', 'shipped', 'shipped', 'cancelled', 'new', 'picking'];

export const ORDERS: Order[] = Array.from({ length: 12 }, (_, i) => ({
  id: `SO-${1040 + i}`,
  customer: CUSTOMERS[i % CUSTOMERS.length],
  items: (i % 4) + 1,
  total: 25 + i * 17.5,
  status: STATUSES[i % STATUSES.length],
}));
