/**
 * AC-DT-6 (`PLAN-oi-decision-trail-ui.md`, round 2 ruling, round 3 review B2): "Raised via"
 * is hidden by default on the Lines tab, same as the worklist. `orderInquiryHeaderLinesColumns.
 * test.tsx`'s own coverage only checks the `DEFAULT_HIDDEN_COLUMNS` constant - it would stay
 * green even if `OrderInquiryLinesTab`'s own `initialState.columnVisibility` wiring were
 * removed, since nothing in that file ever renders the real table. This file does.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
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

function line(overrides: Partial<OrderInquiryWorklistRow> = {}): OrderInquiryWorklistRow {
  return {
    id: 'row-1',
    verb: 'ORDER',
    state: 'raised',
    qty: '10',
    linked_qty: '0',
    bundled_qty: '0',
    ...overrides,
  } as OrderInquiryWorklistRow;
}

function renderTab(lines: OrderInquiryWorklistRow[] = [line()]) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <OrderInquiryLinesTab
        lines={lines}
        isLoading={false}
        rowSelection={{}}
        onRowSelectionChange={() => {}}
      />
    </QueryClientProvider>,
  );
}

describe('OrderInquiryLinesTab: "Raised via" is hidden by default (B2, round 3)', () => {
  it('does not render the "Raised via" column header on first load', async () => {
    renderTab();

    // A visible column's own header renders as soon as the grid mounts.
    expect(await screen.findByRole('columnheader', { name: 'Product' })).toBeInTheDocument();
    expect(screen.queryByRole('columnheader', { name: 'Raised via' })).not.toBeInTheDocument();
  });
});
