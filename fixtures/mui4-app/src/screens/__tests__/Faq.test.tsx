import { fireEvent, screen } from '@testing-library/react';
import { renderScreen } from '../../test-utils';
import { Faq } from '../Faq';

describe('Faq', () => {
  it('reveals an answer when its question is clicked', () => {
    renderScreen(<Faq />);
    const question = screen.getByRole('button', { name: 'Can I delete my account?' });
    expect(question).toHaveAttribute('aria-expanded', 'false');

    fireEvent.click(question);

    expect(question).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText(/This cannot be undone/)).toBeVisible();
  });

  it('links to support', () => {
    renderScreen(<Faq />);

    expect(screen.getByRole('link', { name: 'Contact support' })).toHaveAttribute(
      'href',
      'mailto:support@example.com',
    );
  });
});
