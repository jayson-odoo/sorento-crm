/**
 * OI-WHOLE-SO-CANCEL v2 (B2), red: the Lines tab's empty state tells an OI whose every row is
 * cancelled from one that never had a row.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/project-sales/order-inquiries/oi-1',
  useSearchParams: () => new URLSearchParams(''),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

import { OrderInquiryLinesTab } from './OrderInquiryLinesTab';
import type { OrderInquiryWorklistRow } from '../../../_shared/types/orderInquiry.types';

function line(over: Partial<OrderInquiryWorklistRow>): OrderInquiryWorklistRow {
  return {
    id: 'row-1',
    verb: 'ORDER',
    state: 'raised',
    ack_state: 'awaiting',
    qty: '10',
    linked_qty: '0',
    bundled_qty: '0',
    ...over,
  } as OrderInquiryWorklistRow;
}

function renderTab(lines: OrderInquiryWorklistRow[]) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <OrderInquiryLinesTab lines={lines} isLoading={false} rowSelection={{}} onRowSelectionChange={() => {}} />
    </QueryClientProvider>,
  );
}

describe('B2: the empty state of the Lines tab', () => {
  it('reads "Every line on this order inquiry is cancelled." when every row is cancelled', async () => {
    renderTab([
      line({ id: 'c1', item_code: 'ZZT-C1', core_line_id: 'cl-1', line_no: 1, state: 'cancelled' }),
      line({ id: 'c2', item_code: 'ZZT-C2', core_line_id: 'cl-2', line_no: 2, state: 'cancelled' }),
    ]);
    expect(
      await screen.findByText('Every line on this order inquiry is cancelled.'),
    ).toBeInTheDocument();
    expect(screen.queryByText('Nothing was raised on this order inquiry.')).not.toBeInTheDocument();
  });

  it('still reads "Nothing was raised on this order inquiry." when there are no rows at all', async () => {
    renderTab([]);
    expect(
      await screen.findByText('Nothing was raised on this order inquiry.'),
    ).toBeInTheDocument();
  });
});
