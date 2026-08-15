import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

import { RevisionBanner } from './RevisionBanner';

describe('RevisionBanner', () => {
  it('renders nothing at revision 0', () => {
    const { container } = render(
      <RevisionBanner revisionNo={0} documentNumber="SI-26-0184" reason="typo" />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing when the counter is missing', () => {
    const { container } = render(<RevisionBanner documentNumber="SI-26-0184" />);
    expect(container).toBeEmptyDOMElement();
  });

  it('shows the revision, the suffixed number, who and why once revised', () => {
    render(
      <RevisionBanner
        revisionNo={2}
        documentNumber="SI-26-0184"
        revisedAt="2026-07-12T07:04:00"
        revisedByName="Alex Tan"
        reason="Quantity changed from 5 to 8"
        restartedAtLabel="Project Sales"
      />,
    );
    expect(screen.getByText(/Revision 2/)).toBeInTheDocument();
    expect(screen.getByText(/SI-26-0184-R2/)).toBeInTheDocument();
    expect(screen.getByText('Alex Tan')).toBeInTheDocument();
    expect(screen.getByText(/Quantity changed from 5 to 8/)).toBeInTheDocument();
    expect(screen.getByText(/Work restarted at Project Sales/)).toBeInTheDocument();
  });

  it('renders the timestamp in Malaysia time (UTC+8)', () => {
    render(<RevisionBanner revisionNo={1} revisedAt="2026-07-12T07:04:00" />);
    expect(screen.getByText(/3:04/)).toBeInTheDocument();
    expect(screen.getByText(/pm/i)).toBeInTheDocument();
  });

  it('degrades gracefully when submitter and reason are unknown', () => {
    render(<RevisionBanner revisionNo={1} documentNumber="SI-26-0184" />);
    expect(screen.getByText(/Revision 1/)).toBeInTheDocument();
    expect(screen.queryByText(/ by /)).not.toBeInTheDocument();
  });

  it('is not styled as destructive - a revision is new work, not an error', () => {
    const { container } = render(<RevisionBanner revisionNo={1} reason="x" />);
    const banner = container.firstElementChild as HTMLElement;
    expect(banner.className).not.toMatch(/destructive/);
  });
});
