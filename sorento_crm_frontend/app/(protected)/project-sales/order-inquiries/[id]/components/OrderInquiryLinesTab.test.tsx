/**
 * AC-DT-6 (`PLAN-oi-decision-trail-ui.md`, round 2 ruling, round 3 review B2): "Raised via"
 * is hidden by default on the Lines tab, same as the worklist. `orderInquiryHeaderLinesColumns.
 * test.tsx`'s own coverage only checks the `DEFAULT_HIDDEN_COLUMNS` constant - it would stay
 * green even if `OrderInquiryLinesTab`'s own `initialState.columnVisibility` wiring were
 * removed, since nothing in that file ever renders the real table. This file does.
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

/**
 * `PLAN-oi-no-double-count-25sep.md` S0 (issue #1248), owner rulings 26 Sep 2026: the grid
 * renders ONE row per sales order line (G5), sorted by No., a cancelled line greyed (G7),
 * and a tick selects the line's live rows, never a used one (AC-ND-12).
 */
describe('AC-ND-1 / 2 / 10 / 12: one row per sales order line', () => {
  const rows = [
    line({ id: 'l2-linked', item_code: 'WC200', core_line_id: 'cl-2', line_no: 2, qty: '6', linked_qty: '6', state: 'partly_linked' }),
    line({ id: 'l1-used', item_code: 'CKS1050', core_line_id: 'cl-1', line_no: 1, qty: '2', redirected_to_pool: true }),
    line({ id: 'l1-fresh', item_code: 'CKS1050', core_line_id: 'cl-1', line_no: 1, qty: '5' }),
    line({ id: 'l2-fresh', item_code: 'WC200', core_line_id: 'cl-2', line_no: 2, qty: '4' }),
    line({ id: 'l5', item_code: 'BSN-40', core_line_id: 'cl-5', line_no: 5, qty: '4', line_cancelled: true }),
    line({ id: 'l6-used', item_code: 'TAP-88', core_line_id: 'cl-6', line_no: 6, qty: '3', redirected_to_pool: true }),
  ];

  function renderLines(onRowSelectionChange = vi.fn()) {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <OrderInquiryLinesTab
          lines={rows}
          isLoading={false}
          rowSelection={{}}
          onRowSelectionChange={onRowSelectionChange}
        />
      </QueryClientProvider>,
    );
    return onRowSelectionChange;
  }

  function bodyRows() {
    return screen.getAllByRole('row').filter((row) => row.closest('tbody'));
  }

  it('renders one grid row per line, in line order, with No. and no SO line column', async () => {
    renderLines();
    expect(await screen.findByRole('columnheader', { name: 'No.' })).toBeInTheDocument();
    expect(screen.queryByRole('columnheader', { name: 'SO line' })).not.toBeInTheDocument();
    const products = bodyRows().map((row) => row.textContent ?? '');
    expect(products).toHaveLength(4);
    expect(products[0]).toContain('CKS1050');
    expect(products[1]).toContain('WC200');
    expect(products[2]).toContain('BSN-40');
    expect(products[3]).toContain('TAP-88');
  });

  it('greys a cancelled line and a line with nothing to buy', async () => {
    renderLines();
    await screen.findByText('BSN-40');
    const [first, , cancelled, retired] = bodyRows();
    expect(first.className).not.toContain('opacity-60');
    expect(cancelled.className).toContain('opacity-60');
    expect(retired.className).toContain('opacity-60');
    expect(within(retired).getByRole('checkbox')).toBeDisabled();
  });

  it('ticking a line hands back its live row ids, never the used one', async () => {
    const onChange = renderLines();
    await screen.findByText('CKS1050');
    fireEvent.click(within(bodyRows()[1]).getByRole('checkbox'));
    expect(onChange).toHaveBeenLastCalledWith({ 'l2-linked': true, 'l2-fresh': true });
    fireEvent.click(within(bodyRows()[0]).getByRole('checkbox'));
    expect(onChange).toHaveBeenLastCalledWith({ 'l1-fresh': true });
  });
});
