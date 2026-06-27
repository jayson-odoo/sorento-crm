import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { RejectionReasonBanner } from './RejectionReasonBanner';

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
