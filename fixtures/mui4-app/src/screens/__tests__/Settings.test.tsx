import { fireEvent, screen } from '@testing-library/react';
import { renderScreen } from '../../test-utils';
import { Settings } from '../Settings';

describe('Settings', () => {
  it('enables Save only after a change, and saves the new preferences', () => {
    const onSave = jest.fn();
    renderScreen(<Settings onSave={onSave} />);
    const save = screen.getByRole('button', { name: 'Save changes' });
    expect(save).toBeDisabled();

    fireEvent.click(screen.getByRole('checkbox', { name: 'Product news' }));
    expect(save).toBeEnabled();
    fireEvent.click(save);

    expect(onSave).toHaveBeenCalledWith({ emailDigest: true, productNews: true, darkMode: false });
    expect(screen.getByRole('status')).toHaveTextContent('Settings saved');
    expect(save).toBeDisabled();
  });

  it('shows button text in sentence case, as the theme asks', () => {
    renderScreen(<Settings />);

    // The theme turns off Material's default upper-case button text.
    expect(window.getComputedStyle(screen.getByText('Save changes')).textTransform).toBe('none');
  });
});
