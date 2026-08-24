import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { PersonLink } from './PersonLink';

describe('PersonLink', () => {
  it('renders a wa.me link with the right href + rel when a phone is present (FB-2)', () => {
    render(<PersonLink name="Alice Tan" waPhone="60123456789" />);
    const link = screen.getByRole('link', { name: 'Alice Tan' });
    expect(link).toHaveAttribute('href', 'https://wa.me/60123456789');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    // underlined so a reviewer can see it's a click-to-WhatsApp link
    expect(link.className).toContain('underline');
  });

  it('renders plain text (no anchor) when there is no phone (FB-1)', () => {
    const { container } = render(<PersonLink name="Bob Lee" waPhone={null} />);
    expect(screen.getByText('Bob Lee')).toBeInTheDocument();
    expect(container.querySelector('a')).toBeNull();
  });

  it('renders plain text when the phone is only whitespace/non-digits', () => {
    const { container } = render(<PersonLink name="Bob Lee" waPhone="   " />);
    expect(screen.getByText('Bob Lee')).toBeInTheDocument();
    expect(container.querySelector('a')).toBeNull();
  });

  it('renders nothing when the name is blank/whitespace (FB-3)', () => {
    const { container, rerender } = render(<PersonLink name="   " waPhone="60123456789" />);
    expect(container).toBeEmptyDOMElement();
    rerender(<PersonLink name={null} waPhone="60123456789" />);
    expect(container).toBeEmptyDOMElement();
    rerender(<PersonLink name={undefined} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('strips non-digit characters from the phone before building the href', () => {
    render(<PersonLink name="Carol" waPhone="+60 12-345 6789" />);
    expect(screen.getByRole('link', { name: 'Carol' })).toHaveAttribute(
      'href',
      'https://wa.me/60123456789',
    );
  });

  it('renders a UUID-looking name verbatim as text and never uses it as an href (UUID-2)', () => {
    const uuid = '3f2504e0-4f89-11d3-9a0c-0305e82c3301';
    const { container } = render(<PersonLink name={uuid} waPhone={null} />);
    // The component does not fabricate - it shows exactly what it was given...
    expect(screen.getByText(uuid)).toBeInTheDocument();
    // ...but never as a link (no phone), and never inside an href.
    expect(container.querySelector('a')).toBeNull();
  });

  it('never places a UUID in the href even when a phone is present', () => {
    const uuid = '3f2504e0-4f89-11d3-9a0c-0305e82c3301';
    render(<PersonLink name={uuid} waPhone="60123456789" />);
    const link = screen.getByRole('link', { name: uuid });
    expect(link.getAttribute('href')).toBe('https://wa.me/60123456789');
    expect(link.getAttribute('href')).not.toContain(uuid);
  });
});
