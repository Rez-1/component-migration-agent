import { fireEvent, screen } from '@testing-library/react';
import { renderScreen } from '../../test-utils';
import { UsersTable } from '../UsersTable';

describe('UsersTable', () => {
  it('filters users by name', () => {
    renderScreen(<UsersTable />);
    expect(screen.getAllByRole('row')).toHaveLength(5); // header + 4 users

    fireEvent.change(screen.getByLabelText('Filter by name'), { target: { value: 'grace' } });

    expect(screen.getAllByRole('row')).toHaveLength(2);
    expect(screen.getByRole('cell', { name: 'Grace Hopper' })).toBeInTheDocument();
  });

  it('says so when no user matches', () => {
    renderScreen(<UsersTable />);
    fireEvent.change(screen.getByLabelText('Filter by name'), { target: { value: 'zzz' } });

    expect(screen.getByText('No users match “zzz”.')).toBeInTheDocument();
  });

  it('exports the visible users as CSV', () => {
    const onExport = jest.fn();
    renderScreen(<UsersTable onExport={onExport} />);
    fireEvent.change(screen.getByLabelText('Filter by name'), { target: { value: 'alan' } });

    fireEvent.click(screen.getByRole('button', { name: 'Export CSV' }));

    expect(onExport).toHaveBeenCalledWith('name,email,role\nAlan Turing,alan@example.com,Editor');
  });
});
