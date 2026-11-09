import { screen, within } from '@testing-library/react';
import { renderScreen } from '../../test-utils';
import { StockSummary } from '../StockSummary';

describe('StockSummary', () => {
  it('shows units on hand and open orders', () => {
    renderScreen(<StockSummary figures={{ unitsOnHand: 1520, openOrders: 4, capacityUsed: 40 }} />);

    expect(within(screen.getByRole('article', { name: 'Units on hand' })).getByText('1,520')).toBeInTheDocument();
    expect(within(screen.getByRole('article', { name: 'Open orders' })).getByText('4')).toBeInTheDocument();
  });

  it('shows how much bin capacity is used', () => {
    renderScreen(<StockSummary figures={{ unitsOnHand: 10, openOrders: 0, capacityUsed: 85 }} />);

    expect(screen.getByRole('progressbar', { name: 'Bin capacity used' })).toHaveAttribute('aria-valuenow', '85');
    expect(screen.getByText('85%')).toBeInTheDocument();
  });
});
