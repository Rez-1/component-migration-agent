import { screen } from '@testing-library/react';
import { renderComponent } from '../../test-utils';
import { ProfileCard } from '../ProfileCard';

describe('ProfileCard', () => {
  it('shows the name, role, email and initials', () => {
    renderComponent(<ProfileCard name="Grace Hopper" role="Editor" email="grace@example.com" />);

    const card = screen.getByRole('article', { name: 'Profile of Grace Hopper' });
    expect(card).toHaveTextContent('Grace Hopper');
    expect(card).toHaveTextContent('Editor');
    expect(card).toHaveTextContent('grace@example.com');
    expect(card).toHaveTextContent('GH');
  });
});
