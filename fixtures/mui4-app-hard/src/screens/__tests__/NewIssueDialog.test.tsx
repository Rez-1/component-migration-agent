import { fireEvent, screen, waitFor } from '@testing-library/react';
import { renderScreen } from '../../test-utils';
import { NewIssueDialog } from '../NewIssueDialog';

async function openDialog() {
  fireEvent.click(screen.getByRole('button', { name: 'New issue' }));
  await screen.findByRole('dialog', { name: 'New issue' });
}

describe('NewIssueDialog', () => {
  it('puts the cursor in the title once the dialog is open', async () => {
    renderScreen(<NewIssueDialog />);
    await openDialog();

    await waitFor(() => expect(screen.getByLabelText('Title')).toHaveFocus());
  });

  it('assigns new issues to the signed-in user, marked in the list', async () => {
    renderScreen(<NewIssueDialog />);
    await openDialog();
    const assignee = screen.getByLabelText('Assignee');
    expect(assignee).toHaveValue('Grace Hopper');

    fireEvent.keyDown(assignee, { key: 'ArrowDown' });

    expect(screen.getAllByRole('option')).toHaveLength(4);
    expect(screen.getByRole('option', { name: 'Grace Hopper' })).toHaveAttribute(
      'aria-selected',
      'true'
    );
    expect(screen.getByRole('option', { name: 'Ada Lovelace' })).toHaveAttribute(
      'aria-selected',
      'false'
    );
  });

  it('creates the issue with a tidied estimate', async () => {
    const onCreate = jest.fn();
    renderScreen(<NewIssueDialog onCreate={onCreate} />);
    await openDialog();

    fireEvent.change(screen.getByLabelText('Title'), { target: { value: 'Fix flaky upload test' } });
    const estimate = screen.getByLabelText('Estimate');
    fireEvent.change(estimate, { target: { value: '90m' } });
    fireEvent.blur(estimate);
    expect(estimate).toHaveValue('1h 30m');
    fireEvent.click(screen.getByRole('button', { name: 'Create' }));

    expect(onCreate).toHaveBeenCalledWith({
      title: 'Fix flaky upload test',
      assignee: 'grace',
      reviewer: null,
      estimate: '1h 30m',
    });
  });
});
