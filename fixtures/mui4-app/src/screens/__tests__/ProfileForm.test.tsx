import { fireEvent, screen } from '@testing-library/react';
import { renderScreen } from '../../test-utils';
import { ProfileForm } from '../ProfileForm';

describe('ProfileForm', () => {
  it('saves the display name and the chosen role', () => {
    const onSubmit = jest.fn();
    renderScreen(<ProfileForm onSubmit={onSubmit} />);
    const save = screen.getByRole('button', { name: 'Save profile' });
    expect(save).toBeDisabled();

    fireEvent.change(screen.getByLabelText(/Display name/), { target: { value: 'Ada' } });
    fireEvent.change(screen.getByLabelText('Role'), { target: { value: 'editor' } });
    fireEvent.click(save);

    expect(onSubmit).toHaveBeenCalledWith({ displayName: 'Ada', role: 'editor' });
    expect(screen.getByRole('status')).toHaveTextContent('Saved Ada (Editor)');
  });
});
