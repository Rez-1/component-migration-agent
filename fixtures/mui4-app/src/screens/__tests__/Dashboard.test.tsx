import { screen, within } from '@testing-library/react';
import { renderScreen } from '../../test-utils';
import { Dashboard } from '../Dashboard';

describe('Dashboard', () => {
  it('shows one card per KPI with its value and trend', () => {
    renderScreen(<Dashboard />);

    expect(screen.getByRole('heading', { name: 'Dashboard' })).toBeInTheDocument();
    const users = screen.getByRole('article', { name: 'Active users' });
    expect(within(users).getByText('1,284')).toBeInTheDocument();
    expect(within(users).getByText('Up on last week')).toBeInTheDocument();
    expect(screen.getAllByRole('article')).toHaveLength(3);
  });

  it('renders the KPIs it is given', () => {
    renderScreen(<Dashboard kpis={[{ label: 'Revenue', value: '€12k', trend: 'down' }]} />);

    expect(screen.getByRole('article', { name: 'Revenue' })).toHaveTextContent('€12k');
    expect(screen.getByText('Down on last week')).toBeInTheDocument();
  });
});
