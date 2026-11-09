import { fireEvent, screen, within } from '@testing-library/react';
import { renderScreen } from '../../test-utils';
import { Board } from '../Board';
import { ISSUES } from '../../data/issues';

describe('Board', () => {
  it('filters the cards by status', () => {
    renderScreen(<Board issues={ISSUES} />);
    expect(screen.getAllByRole('heading', { level: 2 })).toHaveLength(12);

    fireEvent.click(screen.getByRole('tab', { name: 'Done (4)' }));

    const cards = screen.getAllByRole('heading', { level: 2 });
    expect(cards).toHaveLength(4);
    expect(cards[0]).toHaveTextContent('#103 Dark mode contrast on badges');
  });

  it('opens an issue from its card', () => {
    const onOpen = jest.fn();
    renderScreen(<Board issues={ISSUES} onOpen={onOpen} />);

    fireEvent.click(screen.getByText('#104 Search ignores accents'));

    expect(onOpen).toHaveBeenCalledWith(104);
  });

  it('shows the selected status tab in bold', () => {
    renderScreen(<Board issues={ISSUES} />);
    const tabs = within(screen.getByRole('tablist', { name: 'Status' }));

    fireEvent.click(tabs.getByRole('tab', { name: 'Open (4)' }));

    expect(tabs.getByRole('tab', { name: 'Open (4)' })).toHaveStyle({ fontWeight: 700 });
    expect(tabs.getByRole('tab', { name: 'All (12)' })).not.toHaveStyle({ fontWeight: 700 });
  });
});
