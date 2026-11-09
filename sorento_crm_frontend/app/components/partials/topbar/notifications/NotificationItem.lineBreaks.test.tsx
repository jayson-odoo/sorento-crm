import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn() }) }));

import NotificationItem from './NotificationItem';

const digest =
  'List price changed for 2 products (08/11/2026):\n' +
  '- A1 Alpha: RM 100.00 -> RM 110.00 (+10.0%)\n' +
  '- B2 Beta: RM 50.00 -> RM 40.00 (-20.0%)\n' +
  'View the list: https://crm.example/master-data-management/products?list_price_batch_id=b1';

describe('NotificationItem body line breaks (PRODUCT-FIELD-CHANGE-NOTIFY)', () => {
  it('keeps the digest lines on their own lines in the bell', () => {
    render(
      <NotificationItem
        item={{
          id: 'n1',
          user_id: 'u1',
          type: 'product_list_price_changed',
          title: 'List price changed for 2 products',
          body: digest,
          data: null,
          read_at: null,
          archived_at: null,
          resolved_at: null,
          created_at: '2026-11-08T00:00:00Z',
          source_entity_type: 'product_list_price_batch',
          source_entity_id: 'b1',
          event_type: 'list_price_changed',
        }}
        onMarkRead={vi.fn()}
        onMarkUnread={vi.fn()}
        onClear={vi.fn()}
        onInvalidate={vi.fn()}
      />,
    );
    const line = screen.getByText(/A1 Alpha: RM 100\.00 -> RM 110\.00/);
    // The newline characters survive in the DOM text...
    const body = line.closest('div') as HTMLElement;
    expect(body.textContent).toContain('\n- B2 Beta');
    // ...and the container renders them as line breaks instead of collapsing them.
    expect(body.className).toContain('whitespace-pre-line');
  });
});
