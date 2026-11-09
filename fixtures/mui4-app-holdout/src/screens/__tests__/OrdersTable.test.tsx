import { fireEvent, screen } from '@testing-library/react';
import { renderScreen } from '../../test-utils';
import { OrdersTable } from '../OrdersTable';
import { ORDERS } from '../../data/orders';

describe('OrdersTable', () => {
  it('lists the first page of orders with their status', () => {
    renderScreen(<OrdersTable />);

    expect(screen.getByRole('cell', { name: 'SO-1040' })).toBeInTheDocument();
    expect(screen.getByRole('cell', { name: 'SO-1044' })).toBeInTheDocument();
    expect(screen.queryByRole('cell', { name: 'SO-1045' })).not.toBeInTheDocument();
    expect(screen.getAllByText('Shipped')).toHaveLength(2);
  });

  it('pages through the orders', () => {
    renderScreen(<OrdersTable />);

    fireEvent.click(screen.getByRole('button', { name: 'Next page' }));

    expect(screen.getByRole('cell', { name: 'SO-1045' })).toBeInTheDocument();
    expect(screen.queryByRole('cell', { name: 'SO-1040' })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Previous page' }));
    expect(screen.getByRole('cell', { name: 'SO-1040' })).toBeInTheDocument();
  });

  it('opens an order when its row is clicked', () => {
    const onOpen = jest.fn();
    renderScreen(<OrdersTable onOpen={onOpen} />);

    fireEvent.click(screen.getByRole('cell', { name: 'SO-1042' }));

    expect(onOpen).toHaveBeenCalledWith(ORDERS[2]);
  });
});
