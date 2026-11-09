import { act, fireEvent, screen } from '@testing-library/react';
import { renderScreen } from '../../test-utils';
import { AccountDialog } from '../AccountDialog';

function clickOutsideDialog() {
  // The dialog's container covers the backdrop; a click on it is a backdrop click.
  const container = document.querySelector('.MuiDialog-container');
  if (!container) throw new Error('dialog container not found');
  fireEvent.mouseDown(container);
  fireEvent.mouseUp(container);
  fireEvent.click(container);
}

describe('AccountDialog', () => {
  beforeEach(() => jest.useFakeTimers());
  afterEach(() => jest.useRealTimers());

  it('deletes only after the confirmation word is typed', () => {
    const onDelete = jest.fn();
    renderScreen(<AccountDialog onDelete={onDelete} />);
    fireEvent.click(screen.getByRole('button', { name: 'Delete account' }));

    const del = screen.getByRole('button', { name: 'Delete' });
    expect(del).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Confirmation'), { target: { value: 'DELETE' } });
    fireEvent.click(del);

    expect(onDelete).toHaveBeenCalledTimes(1);
  });

  it('stays open, keeping what was typed, when the user clicks outside it', () => {
    renderScreen(<AccountDialog />);
    fireEvent.click(screen.getByRole('button', { name: 'Delete account' }));
    fireEvent.change(screen.getByLabelText('Confirmation'), { target: { value: 'DEL' } });

    clickOutsideDialog();
    act(() => {
      jest.advanceTimersByTime(1000); // longer than any close transition
    });

    expect(screen.getByRole('dialog', { name: 'Delete your account?' })).toBeInTheDocument();
    expect(screen.getByLabelText('Confirmation')).toHaveValue('DEL');
  });

  it('closes on Cancel', () => {
    renderScreen(<AccountDialog />);
    fireEvent.click(screen.getByRole('button', { name: 'Delete account' }));

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    act(() => {
      jest.advanceTimersByTime(1000); // longer than any close transition
    });

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});
