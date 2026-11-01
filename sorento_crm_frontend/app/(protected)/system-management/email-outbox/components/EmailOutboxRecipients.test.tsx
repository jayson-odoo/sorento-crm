/** DEALER-OI-ROUTE browser pass: the outbox row detail names To and Cc separately. */
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import EmailOutboxRecipients from './EmailOutboxRecipients';

describe('EmailOutboxRecipients', () => {
  it('shows every To and every Cc on their own lines', () => {
    render(
      <EmailOutboxRecipients
        row={{
          recipient_email: 'a@example.com',
          recipients_json: { to: ['a@example.com', 'b@example.com'], cc: ['c@example.com'], bcc: [] },
        }}
      />,
    );
    expect(screen.getByTestId('outbox-to').textContent).toBe('a@example.com, b@example.com');
    expect(screen.getByTestId('outbox-cc').textContent).toBe('c@example.com');
    expect(screen.queryByTestId('outbox-bcc')).toBeNull();
  });

  it('a row with no recipients list shows its single recipient as To and no Cc', () => {
    render(<EmailOutboxRecipients row={{ recipient_email: 'a@example.com', recipients_json: null }} />);
    expect(screen.getByTestId('outbox-to').textContent).toBe('a@example.com');
    expect(screen.queryByTestId('outbox-cc')).toBeNull();
  });
});
