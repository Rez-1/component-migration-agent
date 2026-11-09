import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { renderScreen } from '../../test-utils';
import { IssueDetail } from '../IssueDetail';
import { ISSUES } from '../../data/issues';

const issue = ISSUES[0]; // #101, labelled "bug"

function labelsInput() {
  return screen.getByLabelText('Labels');
}

function chips() {
  return Array.from(document.querySelectorAll('.MuiChip-label')).map((c) => c.textContent);
}

describe('IssueDetail', () => {
  it('adds a label and says so', () => {
    renderScreen(<IssueDetail issue={issue} />);
    fireEvent.focus(labelsInput());
    fireEvent.change(labelsInput(), { target: { value: 'doc' } });

    fireEvent.click(screen.getByRole('option', { name: 'docs' }));

    expect(chips()).toEqual(['bug', 'docs']);
    expect(screen.getByRole('alert')).toHaveTextContent('Added “docs”');
  });

  it('removes a label with Backspace, and Undo brings it back', () => {
    renderScreen(<IssueDetail issue={issue} />);
    fireEvent.focus(labelsInput());

    fireEvent.keyDown(labelsInput(), { key: 'Backspace' });

    expect(chips()).toEqual([]);
    const notice = screen.getByRole('alert');
    expect(notice).toHaveTextContent('Removed “bug”');
    fireEvent.click(within(notice).getByRole('button', { name: 'Undo' }));
    expect(chips()).toEqual(['bug']);
  });

  it('puts the cursor in the comment box once the dialog is open', async () => {
    const onComment = jest.fn();
    renderScreen(<IssueDetail issue={issue} onComment={onComment} />);

    fireEvent.click(screen.getByRole('button', { name: 'Comment' }));

    const box = within(screen.getByRole('dialog', { name: 'Comment on #101' })).getByLabelText(
      'Comment'
    );
    await waitFor(() => expect(box).toHaveFocus());
    fireEvent.change(box, { target: { value: 'Reproduced on Safari.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Post' }));
    expect(onComment).toHaveBeenCalledWith('Reproduced on Safari.');
  });
});
