import { fireEvent, screen } from '@testing-library/react';
import { renderScreen } from '../../test-utils';
import { IssueList } from '../IssueList';
import { ISSUES } from '../../data/issues';

function titles() {
  return screen
    .getAllByRole('row')
    .slice(1)
    .map((row) => row.children[1].textContent);
}

describe('IssueList', () => {
  it('pages through the issues five at a time', () => {
    renderScreen(<IssueList issues={ISSUES} />);
    expect(titles()).toHaveLength(5);
    expect(titles()[0]).toBe('Login form loses focus on error');
    expect(screen.getByRole('button', { name: 'Previous issues' })).toBeDisabled();

    fireEvent.click(screen.getByRole('button', { name: 'Next issues' }));

    expect(titles()[0]).toBe('Board columns jump on drag');
    expect(screen.getByText(/^6.10 of 12$/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Previous issues' }));
    expect(titles()[0]).toBe('Login form loses focus on error');
  });

  it('opens an issue from its row', () => {
    const onOpen = jest.fn();
    renderScreen(<IssueList issues={ISSUES} onOpen={onOpen} />);

    fireEvent.click(screen.getByText('Export to CSV skips archived issues'));

    expect(onOpen).toHaveBeenCalledWith(102);
  });

  it('shows placeholder rows while loading', () => {
    renderScreen(<IssueList issues={[]} loading />);

    expect(screen.getByRole('table')).toHaveAttribute('aria-busy', 'true');
    expect(screen.getAllByRole('row')).toHaveLength(4);
    expect(screen.queryByText('Login form loses focus on error')).not.toBeInTheDocument();
  });
});
