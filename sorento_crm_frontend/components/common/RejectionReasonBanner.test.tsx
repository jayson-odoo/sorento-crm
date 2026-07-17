import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { RejectionReasonBanner } from './RejectionReasonBanner';
import { formatDateTimeInMalaysia } from '@/lib/helpers';

const RAW_AT = '2026-07-09T01:30:00';

describe('RejectionReasonBanner', () => {
  it('shows the rejection reason when present', () => {
    render(<RejectionReasonBanner reason="the amount is too big" />);
    expect(screen.getByText(/Rejected/)).toBeInTheDocument();
    expect(screen.getByText(/the amount is too big/)).toBeInTheDocument();
  });

  it('renders nothing for null / empty / whitespace reason', () => {
    const { container, rerender } = render(<RejectionReasonBanner reason={null} />);
    expect(container).toBeEmptyDOMElement();
    rerender(<RejectionReasonBanner reason="" />);
    expect(container).toBeEmptyDOMElement();
    rerender(<RejectionReasonBanner reason="   " />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe('RejectionReasonBanner — PersonLink integration (REJ-5 / REJ-6)', () => {
  it('rejectedByName + phone → "Rejected by" with a wa.me anchor around the name + the WHEN', () => {
    const { container } = render(
      <RejectionReasonBanner
        reason="Missing supporting documents"
        rejectedByName="Alice Tan"
        rejectedByWaPhone="60123456789"
        rejectedAt={RAW_AT}
      />,
    );
    const link = screen.getByRole('link', { name: 'Alice Tan' });
    expect(link).toHaveAttribute('href', 'https://wa.me/60123456789');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    expect(container).toHaveTextContent('Rejected by');
    expect(container).toHaveTextContent(formatDateTimeInMalaysia(RAW_AT));
    expect(container).toHaveTextContent('Missing supporting documents');
  });

  it('rejectedByName but NO phone → name is plain text, no anchor', () => {
    const { container } = render(
      <RejectionReasonBanner
        reason="Missing supporting documents"
        rejectedByName="Bob Lee"
        rejectedByWaPhone={null}
        rejectedAt={RAW_AT}
      />,
    );
    expect(screen.getByText('Bob Lee')).toBeInTheDocument();
    expect(container.querySelector('a')).toBeNull();
    expect(container).toHaveTextContent('Rejected by');
    expect(container).toHaveTextContent(formatDateTimeInMalaysia(RAW_AT));
  });

  it('no rejectedByName → falls back to plain "Rejected — {reason}" (no "Rejected by")', () => {
    const { container } = render(
      <RejectionReasonBanner reason="Missing supporting documents" />,
    );
    expect(container).not.toHaveTextContent('Rejected by');
    expect(container).toHaveTextContent('Rejected');
    expect(container).toHaveTextContent('Missing supporting documents');
    expect(container.querySelector('a')).toBeNull();
  });

  it('no reason → renders nothing even when a rejecter is provided', () => {
    const { container } = render(
      <RejectionReasonBanner
        reason=""
        rejectedByName="Alice Tan"
        rejectedByWaPhone="60123456789"
        rejectedAt={RAW_AT}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
