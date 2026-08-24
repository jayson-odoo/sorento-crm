import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

import { SlaExtensionBanner } from './SlaExtensionBanner';
import { formatDateTimeInMalaysia } from '@/lib/helpers';

const RAW_AT = '2026-07-09T01:30:00';

describe('SlaExtensionBanner - PersonLink integration (EXT-2 / EXT-3)', () => {
  it('assignee + assigneeWaPhone → "assigned to" wa.me anchor + the extend WHEN', () => {
    const { container } = render(
      <SlaExtensionBanner
        reason="waiting on supplier confirmation"
        tier={2}
        assignee="Jane Tan"
        assigneeWaPhone="60123456789"
        eventAt={RAW_AT}
      />,
    );
    const link = screen.getByRole('link', { name: 'Jane Tan' });
    expect(link).toHaveAttribute('href', 'https://wa.me/60123456789');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    expect(container).toHaveTextContent('assigned to');
    expect(container).toHaveTextContent(formatDateTimeInMalaysia(RAW_AT));
    expect(container).toHaveTextContent('waiting on supplier confirmation');
  });

  it('assignee without phone → plain text, no anchor', () => {
    const { container } = render(
      <SlaExtensionBanner
        reason="waiting on supplier confirmation"
        tier={2}
        assignee="Jane Tan"
        assigneeWaPhone={null}
        eventAt={RAW_AT}
      />,
    );
    expect(screen.getByText('Jane Tan')).toBeInTheDocument();
    expect(container.querySelector('a')).toBeNull();
    expect(container).toHaveTextContent('assigned to');
  });

  it('empty reason → renders nothing (EXT-3)', () => {
    const { container } = render(
      <SlaExtensionBanner
        reason=""
        assignee="Jane Tan"
        assigneeWaPhone="60123456789"
        eventAt={RAW_AT}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
