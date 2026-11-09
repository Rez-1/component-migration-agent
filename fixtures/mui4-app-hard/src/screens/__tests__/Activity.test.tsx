import { fireEvent, screen, within } from '@testing-library/react';
import { renderScreen } from '../../test-utils';
import { Activity } from '../Activity';

describe('Activity', () => {
  it('lists the latest activity', () => {
    renderScreen(<Activity />);
    const items = within(screen.getByRole('list', { name: 'Activity feed' })).getAllByRole(
      'listitem'
    );
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent('closed #103Ada Lovelace');
  });

  it('adds an update and moves focus to it', () => {
    renderScreen(<Activity />);

    fireEvent.change(screen.getByLabelText('Post an update'), {
      target: { value: 'deployed 2.4 to staging' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Post' }));

    const items = within(screen.getByRole('list', { name: 'Activity feed' })).getAllByRole(
      'listitem'
    );
    expect(items).toHaveLength(3);
    expect(items[2]).toHaveTextContent('deployed 2.4 to staging');
    expect(items[2]).toHaveFocus();
    expect(screen.getByLabelText('Post an update')).toHaveValue('');
  });
});
