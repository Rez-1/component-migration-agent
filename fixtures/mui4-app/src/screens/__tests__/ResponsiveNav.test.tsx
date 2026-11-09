import { fireEvent, screen } from '@testing-library/react';
import { mockViewportWidth, renderScreen } from '../../test-utils';
import { ResponsiveNav } from '../ResponsiveNav';

const PAGES = ['Dashboard', 'Users', 'Help'];

describe('ResponsiveNav', () => {
  it('shows tabs on a desktop screen', async () => {
    mockViewportWidth(1280);
    const onNavigate = jest.fn();
    renderScreen(<ResponsiveNav pages={PAGES} current="Dashboard" onNavigate={onNavigate} />);

    fireEvent.click(await screen.findByRole('tab', { name: 'Users' }));

    expect(onNavigate).toHaveBeenCalledWith('Users');
    expect(screen.queryByRole('button', { name: 'Open menu' })).not.toBeInTheDocument();
  });

  it('uses a menu on a small tablet (920px wide)', async () => {
    mockViewportWidth(920);
    const onNavigate = jest.fn();
    renderScreen(<ResponsiveNav pages={PAGES} current="Dashboard" onNavigate={onNavigate} />);

    fireEvent.click(await screen.findByRole('button', { name: 'Open menu' }));
    fireEvent.click(screen.getByRole('button', { name: 'Help' }));

    expect(onNavigate).toHaveBeenCalledWith('Help');
    expect(screen.queryByRole('tab')).not.toBeInTheDocument();
  });
});
