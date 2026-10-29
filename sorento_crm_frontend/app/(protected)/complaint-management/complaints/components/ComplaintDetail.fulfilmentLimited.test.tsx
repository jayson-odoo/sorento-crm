/**
 * PORTAL-P4-REQUESTS owner hand test 2 (A): a salesperson limited to their own complaints sees that
 * complaint's fulfilment DOs, read-only, below the portal form: DO numbers as plain text, no edit / link /
 * unlink action, no anchor to a DO page they cannot open. The staff detail is pinned by
 * ComplaintDetail.requestScope.test.tsx (staff action set unchanged).
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/hooks/useRequestScope', () => ({
  useRequestScope: () => ({ limited: true, isLoading: false }),
}));
vi.mock('@/components/common/MyRequestPortalForm', () => ({
  __esModule: true,
  default: () => <div data-testid="portal-form">portal form</div>,
}));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(''),
}));
vi.mock('next/link', () => ({
  default: ({ href, children, ...rest }: any) => (
    <a href={typeof href === 'string' ? href : '#'} {...rest}>
      {children}
    </a>
  ),
}));
vi.mock('../services/complaintFulfilmentService', () => ({
  getComplaintFulfilmentOrders: vi.fn(async () => [
    {
      order_id: 'o-1',
      order_number: 'REPPS2605-0012',
      status: 'delivered',
      status_label: 'Delivered',
      actual_delivery_date: '2026-06-02T09:00:00',
      is_cancelled: false,
      items: [{ product_code: 'SKU-1', product_type: 'Mattress', qty: 2 }],
    },
  ]),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

import ComplaintDetail from './ComplaintDetail';

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ComplaintDetail complaintId="cmp-1" />
    </QueryClientProvider>,
  );
}

describe('ComplaintDetail, limited user, fulfilment DOs', () => {
  it('shows the portal form and, below it, the complaint fulfilment DO number as plain text', async () => {
    const { container } = mount();
    expect(screen.getByTestId('portal-form')).toBeInTheDocument();
    const number = await screen.findByText('REPPS2605-0012');
    // Plain text: not inside an anchor.
    expect(number.closest('a')).toBeNull();
    // Below the form.
    const form = screen.getByTestId('portal-form');
    expect(form.compareDocumentPosition(number) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(container.querySelector('a[href*="/order"]')).toBeNull();
  });

  it('is read-only: no edit / link / unlink / delete action', async () => {
    const { container } = mount();
    await screen.findByText('REPPS2605-0012');
    expect(container.querySelectorAll('a').length).toBe(0);
    for (const b of screen.queryAllByRole('button')) {
      const name = (b.getAttribute('aria-label') || b.textContent || '').trim();
      expect(name, `unexpected action "${name}"`).not.toMatch(/edit|link|unlink|delete|remove|add/i);
    }
    expect(within(container).queryByText(/unlink/i)).toBeNull();
  });
});
