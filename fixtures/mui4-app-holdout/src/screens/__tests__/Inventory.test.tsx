import { screen } from '@testing-library/react';
import { renderScreen } from '../../test-utils';
import { Inventory } from '../Inventory';

describe('Inventory', () => {
  it('lists products with their stock and bin', () => {
    renderScreen(<Inventory />);

    expect(screen.getByRole('heading', { name: 'Inventory' })).toBeInTheDocument();
    expect(screen.getByText('Enamel mug (MUG-001)')).toBeInTheDocument();
    expect(screen.getByText('140 in bin A-01')).toBeInTheDocument();
    expect(screen.getByText('Out of stock, bin B-11')).toBeInTheDocument();
  });

  it('shows placeholders while loading', () => {
    renderScreen(<Inventory loading />);

    expect(screen.getByRole('region', { name: 'Inventory' })).toHaveAttribute('aria-busy', 'true');
    expect(screen.getByTestId('inventory-loading').children).toHaveLength(3);
    expect(screen.queryByText('Enamel mug (MUG-001)')).not.toBeInTheDocument();
  });
});
