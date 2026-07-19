import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { VoidBanner } from './VoidBanner';

describe('VoidBanner', () => {
  it('renders nothing when the form is not voided', () => {
    const { container } = render(
      <VoidBanner voided={false} voidedByName="Alex Tan" voidReason="duplicate" />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('shows voided-by name and reason when voided', () => {
    render(
      <VoidBanner
        voided
        voidedByName="Alex Tan"
        voidedAt="2026-07-12T07:04:00"
        voidReason="Duplicate submission"
      />,
    );
    expect(screen.getByText(/Voided/)).toBeInTheDocument();
    expect(screen.getByText('Alex Tan')).toBeInTheDocument();
    expect(screen.getByText(/Duplicate submission/)).toBeInTheDocument();
  });

  it('renders the timestamp in Malaysia time (UTC+8)', () => {
    // 07:04 UTC -> 15:04 (3:04 pm) Malaysia.
    render(<VoidBanner voided voidedAt="2026-07-12T07:04:00" />);
    expect(screen.getByText(/3:04/)).toBeInTheDocument();
    expect(screen.getByText(/pm/i)).toBeInTheDocument();
  });

  it('degrades gracefully when actor / reason are missing', () => {
    render(<VoidBanner voided />);
    // Still shows the "Voided" label, just no "by" / reason clauses.
    expect(screen.getByText(/Voided/)).toBeInTheDocument();
    expect(screen.queryByText(/ by /)).not.toBeInTheDocument();
  });

  it('uses a neutral gray (non-destructive) style', () => {
    const { container } = render(<VoidBanner voided voidReason="x" />);
    const banner = container.firstElementChild as HTMLElement;
    expect(banner.className).toMatch(/bg-gray-100/);
    // Must NOT reuse the destructive/red rejection styling.
    expect(banner.className).not.toMatch(/destructive/);
  });
});
