import { fireEvent, screen } from '@testing-library/react';
import { renderScreen } from '../../test-utils';
import { Search } from '../Search';

function typeCity(text: string) {
  const input = screen.getByLabelText('City');
  fireEvent.focus(input); // the user clicks into the field first
  fireEvent.change(input, { target: { value: text } });
}

describe('Search', () => {
  it('suggests matching cities with their country', () => {
    renderScreen(<Search />);

    typeCity('dam');

    const options = screen.getAllByRole('option');
    expect(options).toHaveLength(2);
    expect(options[0]).toHaveTextContent('AmsterdamNetherlands');
    expect(options[1]).toHaveTextContent('RotterdamNetherlands');
  });

  it('selects Amsterdam', () => {
    const onSelect = jest.fn();
    renderScreen(<Search onSelect={onSelect} />);

    typeCity('Ams');
    fireEvent.click(screen.getByRole('option', { name: /Amsterdam/ }));

    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ id: 'ams' }));
    expect(screen.getByRole('status')).toHaveTextContent('Selected office: Amsterdam, Netherlands');
    expect(screen.getByLabelText('City')).toHaveValue('Amsterdam');
  });
});
