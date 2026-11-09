import { fireEvent, screen } from '@testing-library/react';
import { mockViewportWidth, renderScreen } from '../../test-utils';
import { OrderDialog } from '../OrderDialog';

const ORDER = { id: 'SO-2001', customer: 'Nordic Tools', items: 3, total: 89.5, status: 'new' as const };

describe('OrderDialog', () => {
  it('shows the order and closes', async () => {
    mockViewportWidth(1280);
    const onClose = jest.fn();
    renderScreen(<OrderDialog order={ORDER} open onClose={onClose} />);

    const dialog = await screen.findByRole('dialog', { name: 'Order SO-2001' });
    expect(dialog).toHaveTextContent('3 items, €89.50');
    expect(dialog).not.toHaveClass('MuiDialog-paperFullScreen');

    fireEvent.click(screen.getByRole('button', { name: 'Close' }));
    expect(onClose).toHaveBeenCalled();
  });

  it('takes the whole screen on a small tablet (700px wide)', async () => {
    mockViewportWidth(700);
    renderScreen(<OrderDialog order={ORDER} open onClose={() => undefined} />);

    expect(await screen.findByRole('dialog', { name: 'Order SO-2001' })).toHaveClass('MuiDialog-paperFullScreen');
  });
});
