import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

import { SlaEscalationBanner } from './SlaEscalationBanner';
import { formatDateTimeInMalaysia } from '@/lib/helpers';

const RAW_AT = '2026-07-09T01:30:00';

describe('SlaEscalationBanner - PersonLink integration (ESC-4..ESC-6)', () => {
  it('escalatedFromName + phone → "escalated from" wa.me anchor + the WHEN', () => {
    const { container } = render(
      <SlaEscalationBanner
        reason="manual: no response from owner"
        tier={2}
        assignee="Sarah Lim"
        escalatedFromName="Jane Tan"
        escalatedFromWaPhone="60123456789"
        escalatedAt={RAW_AT}
      />,
    );
    const link = screen.getByRole('link', { name: 'Jane Tan' });
    expect(link).toHaveAttribute('href', 'https://wa.me/60123456789');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    expect(container).toHaveTextContent('escalated from');
    expect(container).toHaveTextContent(formatDateTimeInMalaysia(RAW_AT));
    // The "manual:" prefix is stripped and the clean reason shows.
    expect(container).toHaveTextContent('no response from owner');
    // Current assignee stays plain context text (never a link).
    expect(container).toHaveTextContent('now assigned to Sarah Lim');
  });

  it('escalatedFromName without phone → plain text, no anchor', () => {
    const { container } = render(
      <SlaEscalationBanner
        reason="no response from owner"
        tier={2}
        escalatedFromName="Jane Tan"
        escalatedFromWaPhone={null}
        escalatedAt={RAW_AT}
      />,
    );
    expect(screen.getByText('Jane Tan')).toBeInTheDocument();
    expect(container.querySelector('a')).toBeNull();
    expect(container).toHaveTextContent('escalated from');
  });

  it('empty reason → renders nothing (existing behaviour, ESC-6)', () => {
    const { container } = render(
      <SlaEscalationBanner
        reason=""
        escalatedFromName="Jane Tan"
        escalatedFromWaPhone="60123456789"
        escalatedAt={RAW_AT}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
