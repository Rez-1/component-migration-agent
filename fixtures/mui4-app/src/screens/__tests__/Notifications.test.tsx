import { fireEvent, screen } from '@testing-library/react';
import { renderScreen } from '../../test-utils';
import { Notifications } from '../Notifications';

describe('Notifications', () => {
  it('announces the unread count and marks everything as read', () => {
    renderScreen(<Notifications />);
    expect(screen.getByText('3 unread notifications')).toBeInTheDocument();
    expect(screen.getAllByText('Unread')).toHaveLength(3);

    fireEvent.click(screen.getByRole('button', { name: 'Mark all as read' }));

    expect(screen.getByText('No unread notifications')).toBeInTheDocument();
    expect(screen.queryByText('Unread')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Mark all as read' })).toBeDisabled();
  });
});
