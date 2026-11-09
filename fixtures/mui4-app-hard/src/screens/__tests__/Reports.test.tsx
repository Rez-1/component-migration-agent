import { fireEvent, screen, within } from '@testing-library/react';
import { renderScreen } from '../../test-utils';
import { Reports } from '../Reports';
import { ISSUES } from '../../data/issues';

function groups() {
  return within(screen.getByRole('list', { name: 'Groups' }))
    .getAllByRole('listitem')
    .map((item) => item.textContent);
}

describe('Reports', () => {
  it('counts the issues by priority', () => {
    renderScreen(<Reports issues={ISSUES} />);

    expect(screen.getByText('12 issues')).toBeInTheDocument();
    expect(groups()).toEqual(['high4 issues', 'low4 issues', 'medium4 issues']);
    const thumbs = screen.getAllByRole('slider');
    expect(thumbs.map((t) => t.getAttribute('aria-valuenow'))).toEqual(['0', '30']);
  });

  it('groups by assignee across pages', () => {
    renderScreen(<Reports issues={ISSUES} />);

    fireEvent.click(screen.getByRole('button', { name: 'By assignee' }));

    expect(screen.getByRole('button', { name: 'By assignee' })).toHaveAttribute(
      'aria-pressed',
      'true'
    );
    expect(groups()).toEqual(['Ada Lovelace3 issues', 'Grace Hopper3 issues', 'Linus Torvalds3 issues']);
    fireEvent.click(screen.getByRole('button', { name: 'Go to page 2' }));
    expect(groups()).toEqual(['Unassigned3 issues']);
  });
});
