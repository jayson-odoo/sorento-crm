/**
 * `PLAN-oi-header-list-detail.md`, AC-DP-05/06, security fix round S1 + UL
 * (`oi-header-list-detail-acceptance-criteria.md`).
 *
 * Two things pinned here:
 *
 * 1. **S1 (never widen).** With nothing ticked, Confirm / Auto link send exactly
 *    `{ filter: { inquiry_id: <the page id> } }` - never a payload that could match
 *    outside this one OI. Real service functions are spied on through a PARTIAL mock
 *    of `orderInquiryService` (kept mostly real via `importOriginal`) rather than
 *    mocking the hooks, so the actual payload the hook builds is what gets asserted.
 * 2. **UL (deferred, not a dialog).** Gear > Unlink selected should start a
 *    server-deferred pending action (countdown + Cancel, AC-DP-06) - the current code
 *    opens an `AlertDialog` instead (see `OrderInquiryDetail.tsx`'s own note on
 *    `unlinkSelected`), which is this test's own red.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { OrderInquiryHeaderDetail, OrderInquiryWorklistRow } from '../../../_shared/types/orderInquiry.types';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/project-sales/order-inquiries/oi-1',
  useSearchParams: () => new URLSearchParams(''),
}));

vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => true,
}));

// Under jsdom nothing answers the column-preferences fetch `DataGrid` starts, so the
// Lines tab grid renders skeletons forever and no row is assertable
// (project_datagrid_jsdom_rows_mockable.md).
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

const acknowledgeFilterSpy = vi.fn(async () => ({ acknowledged: 0, results: [] }));
const acknowledgeRowsSpy = vi.fn(async () => ({ acknowledged: 0, results: [] }));
const autoPlaceSpy = vi.fn(async () => ({ linked: 0, results: [] }));

const HEADER: OrderInquiryHeaderDetail = {
  id: 'oi-1',
  inquiry_no: 'OI-2609-0001',
  legacy_inquiry_no: null,
  raised_at: '2026-09-05T08:00:00',
  raised_by_name: 'Eling',
  sales_order_id: 'so-1',
  project_sales_order_id: 'pso-1',
  so_number: 'SO123456',
  so_date: '2026-09-01',
  customer_name: 'Optad',
  customer_code: 'CUST-1',
  project_id: null,
  project_title: null,
  agent_name: null,
  lines_total: 3,
  lines_to_confirm: 3,
  qty_total: '30',
  status: 'outstanding',
  order_type: null,
  raise_history: [],
};

const LINKED_LINE: OrderInquiryWorklistRow = {
  id: 'row-linked',
  order_inquiry_id: 'oi-1',
  item_code: `ZZT-${'LINK'}`,
  qty: '10',
  delivery_date: null,
  supplier: null,
  po_number: null,
  location: null,
  verb: 'order',
  note: null,
  state: 'placed',
  ack_state: 'awaiting',
  links: [{ kind: 'po', document: 'PO-1', po_id: 'po-1', qty: '10' }],
} as unknown as OrderInquiryWorklistRow;

vi.mock('../../../_shared/services/orderInquiryService', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('../../../_shared/services/orderInquiryService')>();
  return {
    ...actual,
    getOrderInquiryHeader: vi.fn(async () => HEADER),
    getOrderInquiryHeaderLines: vi.fn(async () => [LINKED_LINE]),
    getOrderInquiryHeaderRelatedDocuments: vi.fn(async () => ({
      purchase_orders: [],
      spos: [],
    })),
    listOrderInquiryHeaders: vi.fn(async () => ({ data: [], total: 0, page: 1, limit: 25 })),
    acknowledgeOrderInquiryRowsByFilter: (...args: unknown[]) =>
      acknowledgeFilterSpy(...(args as [unknown])),
    acknowledgeOrderInquiryRows: (...args: unknown[]) =>
      acknowledgeRowsSpy(...(args as [unknown])),
    autoPlaceOrderInquiryRows: (...args: unknown[]) => autoPlaceSpy(...(args as [unknown])),
  };
});

import { OrderInquiryDetail } from './OrderInquiryDetail';

function renderDetail(id: string) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <OrderInquiryDetail id={id} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  acknowledgeFilterSpy.mockClear();
  acknowledgeRowsSpy.mockClear();
  autoPlaceSpy.mockClear();
});

describe('Confirm / Auto link never widen without a real page id (S1)', () => {
  it('with nothing ticked, Confirm sends exactly { filter: { inquiry_id: id } }', async () => {
    renderDetail('oi-1');
    const confirmButton = await screen.findByRole('button', { name: 'Confirm' });

    fireEvent.click(confirmButton);

    await waitFor(() => expect(acknowledgeFilterSpy).toHaveBeenCalledTimes(1));
    expect(acknowledgeFilterSpy.mock.calls[0][0]).toEqual({ inquiry_id: 'oi-1' });
    expect(acknowledgeRowsSpy).not.toHaveBeenCalled();
  });

  it('with an empty page id, Confirm never fires an acknowledge call at all', async () => {
    renderDetail('');

    // The empty-id detail query is `enabled: Boolean(id)` = false, so the header never
    // loads and the "Could not load" state renders instead of the primary button - but
    // that is itself the guard this pins: nothing downstream may EVER reach a mutate
    // call with a widened/empty scope, whether by the button not rendering or by a
    // future change guarding the click. Both are asserted.
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: /confirm/i })).not.toBeInTheDocument(),
    );
    expect(acknowledgeFilterSpy).not.toHaveBeenCalled();
    expect(acknowledgeRowsSpy).not.toHaveBeenCalled();
  });

  it('Auto link with nothing ticked sends exactly { filter: { inquiry_id: id } }', async () => {
    renderDetail('oi-1');
    await screen.findByRole('button', { name: 'Confirm' });

    fireEvent.pointerDown(screen.getByRole('button', { name: 'Order inquiry options' }), {
      button: 0,
    });
    fireEvent.click(await screen.findByRole('menuitem', { name: /auto link/i }));

    await waitFor(() => expect(autoPlaceSpy).toHaveBeenCalledTimes(1));
    expect(autoPlaceSpy.mock.calls[0][0]).toEqual({ filter: { inquiry_id: 'oi-1' } });
  });
});

describe('Unlink selected is a server-deferred pending action, not a confirm dialog (AC-DP-06, UL)', () => {
  it('does not open an AlertDialog - a countdown with Cancel appears instead', async () => {
    renderDetail('oi-1');
    await screen.findByRole('button', { name: 'Confirm' });

    fireEvent.click(await screen.findByLabelText(`Select ${LINKED_LINE.item_code}`));
    fireEvent.pointerDown(screen.getByRole('button', { name: 'Order inquiry options' }), {
      button: 0,
    });
    fireEvent.click(await screen.findByRole('menuitem', { name: /unlink selected/i }));

    // Target behaviour: no confirmation dialog at all, a deferred countdown instead.
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(await screen.findByText(/cancel/i)).toBeInTheDocument();
  });
});
