import { fireEvent, screen } from '@testing-library/react';
import { renderScreen } from '../../test-utils';
import { ProductTags } from '../ProductTags';

describe('ProductTags', () => {
  it('stores a new tag lower-case and hyphenated', () => {
    const onChange = jest.fn();
    renderScreen(<ProductTags sku="MUG-001" initial={['fragile']} onChange={onChange} />);

    const input = screen.getByLabelText('Tags');
    fireEvent.change(input, { target: { value: '  Keep Dry ' } });
    fireEvent.keyDown(input, { key: 'Enter' });

    expect(onChange).toHaveBeenLastCalledWith(['fragile', 'keep-dry']);
    expect(screen.getByRole('button', { name: 'keep-dry' })).toBeInTheDocument();
  });

  it('says which tag was removed', () => {
    renderScreen(<ProductTags sku="MUG-001" initial={['oversize', 'fragile']} />);

    fireEvent.keyDown(screen.getByLabelText('Tags'), { key: 'Backspace' });

    expect(screen.getByRole('status')).toHaveTextContent('Removed fragile');
    expect(screen.queryByRole('button', { name: 'fragile' })).not.toBeInTheDocument();
  });
});
