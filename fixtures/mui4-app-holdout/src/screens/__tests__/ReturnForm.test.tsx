import { fireEvent, screen } from '@testing-library/react';
import { renderScreen } from '../../test-utils';
import { ReturnForm } from '../ReturnForm';

describe('ReturnForm', () => {
  it('logs a return with its reason', () => {
    const onSubmit = jest.fn();
    renderScreen(<ReturnForm onSubmit={onSubmit} />);

    fireEvent.change(screen.getByRole('textbox', { name: /Order number/ }), { target: { value: ' SO-1041 ' } });
    fireEvent.change(screen.getByRole('textbox', { name: 'Reason' }), { target: { value: 'Wrong size' } });
    fireEvent.click(screen.getByRole('button', { name: 'Log return' }));

    expect(onSubmit).toHaveBeenCalledWith({ orderId: 'SO-1041', reason: 'Wrong size', damaged: false });
  });

  it('sends damaged items to inspection', () => {
    const onSubmit = jest.fn();
    renderScreen(<ReturnForm onSubmit={onSubmit} />);

    fireEvent.change(screen.getByRole('textbox', { name: /Order number/ }), { target: { value: 'SO-1047' } });
    fireEvent.click(screen.getByRole('checkbox', { name: 'Item arrived damaged' }));
    fireEvent.click(screen.getByRole('button', { name: 'Send to inspection' }));

    expect(onSubmit).toHaveBeenCalledWith({ orderId: 'SO-1047', reason: '', damaged: true });
  });
});
