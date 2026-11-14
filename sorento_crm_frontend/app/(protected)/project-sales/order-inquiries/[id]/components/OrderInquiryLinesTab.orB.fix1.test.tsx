/**
 * SPARE-PART-OR-B fix round 1 (browser pass), red-first. Item 12: the OI page highlights the
 * row named by `?row=` for a spare part line the same way it does for an SO line. Mirrors
 * `OrderInquiryLinesTab.deepLinkPage.test.tsx` (the SO path: the target's `tr` carries
 * `deep-link-highlight` and the page holding it opens). The OR "OI" link lands here as
 * `/project-sales/order-inquiries/<id>?row=<row id>` (U3.2).
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;

const nav = vi.hoisted(() => ({ params: 'row=row-40' }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/project-sales/order-inquiries/oi-1',
  useSearchParams: () => new URLSearchParams(nav.params),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
vi.mock('@/lib/toast', () => ({
  toast: { info: vi.fn(), success: vi.fn(), error: vi.fn(), warning: vi.fn(), dismiss: vi.fn() },
}));
const ok = (b: unknown) =>
  new Response(JSON.stringify(b), { status: 200, headers: { 'content-type': 'application/json' } });
vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  apiFetch: vi.fn(async () => ok({})),
}));

import { OrderInquiryLinesTab } from './OrderInquiryLinesTab';
import type { OrderInquiryWorklistRow } from '../../../_shared/types/orderInquiry.types';

function lines(count: number): OrderInquiryWorklistRow[] {
  return Array.from({ length: count }, (_, index) => {
    const no = index + 1;
    return {
      id: `row-${no}`,
      order_inquiry_id: 'oi-1',
      inquiry_no: 'OR-2611-0003',
      oi_no: 'OI-2611-0001',
      inquiry_type: 'spare_part_request',
      line_no: no,
      item_code: `ZZX-${String(no).padStart(3, '0')}`,
      product_id: `prod-${no}`,
      verb: 'REPLENISH',
      state: 'raised',
      ack_state: 'awaiting',
      qty: '4',
      unit_price: '10.0000',
      line_total: '40.0000',
      submitted_qty: '4',
      submitted_unit_price: '10.0000',
      photo_changes: { added: 0, removed: 0 },
      linked_qty: '0',
      bundled_qty: '0',
      links: [],
    } as unknown as OrderInquiryWorklistRow;
  });
}

function tab(rows: OrderInquiryWorklistRow[]) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <OrderInquiryLinesTab
        lines={rows}
        isLoading={false}
        rowSelection={{}}
        onRowSelectionChange={() => {}}
        sparePart={{ headerState: 'raised', canDecide: false, canEditPhotos: false, currency: 'MYR' }}
      />
    </QueryClientProvider>,
  );
}

describe('item 12: ?row= highlights a spare part line on the OI page', () => {
  it('a short request: the named line is highlighted', async () => {
    nav.params = 'row=row-3';
    tab(lines(5));
    const target = await screen.findByText('ZZX-003', {}, { timeout: 5000 });
    expect(target.closest('tr')).toHaveClass('deep-link-highlight');
    expect(screen.getByText('ZZX-001').closest('tr')).not.toHaveClass('deep-link-highlight');
  });

  it('a long request: lands on the page holding line 40 of 60, highlighted', async () => {
    nav.params = 'row=row-40';
    tab(lines(60));
    const target = await screen.findByText('ZZX-040', {}, { timeout: 5000 });
    expect(target.closest('tr')).toHaveClass('deep-link-highlight');
    expect(screen.queryByText('ZZX-001')).toBeNull();
  });
});
