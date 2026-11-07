/**
 * OI-RESERVE-ANY-ROW (review S2): the wiring. Ticking a line on the OI page hands
 * `RequestReserveDialog` the rows `reserveRowsOfLines` picks: every reservable ORDER row of a
 * split line, ONE row for a line whose ORDER and DELAY rows are both live (the buy row), and the
 * DELAY row of a line where it is the only live row (OI-2609-0257 line 7). Same harness as
 * `OrderInquiryDetail.reserveRemaining.test.tsx`; the dialog itself is replaced by a probe.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type {
  OrderInquiryHeaderDetail,
  OrderInquiryWorklistRow,
} from '../../../_shared/types/orderInquiry.types';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/project-sales/order-inquiries/oi-1',
  useSearchParams: () => new URLSearchParams(''),
}));

vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => true,
}));

// S1 (reviewer round): `OrderInquiryDetail` reads `useSession` directly now.
vi.mock('next-auth/react', () => ({
  useSession: () => ({ data: { user: { id: 'test-current-user' } }, status: 'authenticated' }),
}));

// Under jsdom nothing answers the column-preferences fetch `DataGrid` starts, so the
// Lines tab grid renders skeletons forever and no row is assertable
// (project_datagrid_jsdom_rows_mockable.md).
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

// Radix Tooltip only mounts TooltipContent's portal on hover, which a plain render+query
// cannot see (`orderInquiryWorklistColumns.test.tsx`'s own precedent) - rendered inline
// instead so the disabled menu item's own reason is queryable without simulating hover.
vi.mock('@/components/ui/tooltip', async () => {
  const actual = await vi.importActual<typeof import('@/components/ui/tooltip')>(
    '@/components/ui/tooltip',
  );
  return {
    ...actual,
    TooltipContent: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  };
});

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
  lines_total: 2,
  lines_to_confirm: 0,
  qty_total: '30',
  status: 'outstanding',
  order_type: null,
  raise_history: [],
};

function reserveRow(over: Partial<OrderInquiryWorklistRow>): OrderInquiryWorklistRow {
  return {
    id: 'row-partial',
    order_inquiry_id: 'oi-1',
    item_code: 'ZZT-PARTIAL',
    qty: '139',
    delivery_date: null,
    supplier: null,
    po_number: null,
    // No stock location on either fixture row: `useReserveRowOptions` short-circuits to
    // its own empty result with no network call at all when a row carries neither a
    // location nor a product id, which is all this test needs - the Requested field's
    // default/max, never the Location select.
    location: null,
    product_id: null,
    verb: 'ORDER',
    note: null,
    state: 'raised',
    ack_state: 'awaiting',
    links: [],
    linked_qty: '0',
    bundled_qty: '0',
    reserved_qty: '0',
    reserve_state: null,
    so_line_id: 'sol-1',
    ...over,
  } as unknown as OrderInquiryWorklistRow;
}

const ROWS = [
  reserveRow({ id: 'split-a', item_code: 'ZZT-SPLIT', so_line_id: 'sol-1', line_no: 1, qty: '10' }),
  reserveRow({ id: 'split-b', item_code: 'ZZT-SPLIT', so_line_id: 'sol-1', line_no: 1, qty: '12' }),
  reserveRow({ id: 'both-order', item_code: 'ZZT-BOTH', so_line_id: 'sol-2', line_no: 2, qty: '22' }),
  reserveRow({ id: 'both-delay', item_code: 'ZZT-BOTH', so_line_id: 'sol-2', line_no: 2, qty: '33', verb: 'DELAY', ack_state: 'acknowledged' }),
  reserveRow({ id: 'l7-used', item_code: 'ZZT-L7', so_line_id: 'sol-7', line_no: 7, qty: '55', redirected_to_pool: true, ack_state: 'acknowledged' }),
  reserveRow({ id: 'l7-delay', item_code: 'ZZT-L7', so_line_id: 'sol-7', line_no: 7, qty: '33', verb: 'DELAY', ack_state: 'acknowledged' }),
];

vi.mock('../../../_shared/services/orderInquiryService', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('../../../_shared/services/orderInquiryService')>();
  return {
    ...actual,
    getOrderInquiryHeader: vi.fn(async () => HEADER),
    getOrderInquiryHeaderLines: vi.fn(async () => ROWS),
    getOrderInquiryHeaderRelatedDocuments: vi.fn(async () => ({ purchase_orders: [], spos: [] })),
    listOrderInquiryHeaders: vi.fn(async () => ({ data: [], total: 0, page: 1, limit: 25 })),
    acknowledgeOrderInquiryRowsByFilter: vi.fn(async () => ({ acknowledged: 0, results: [] })),
    acknowledgeOrderInquiryRows: vi.fn(async () => ({ acknowledged: 0, results: [] })),
    autoPlaceOrderInquiryRows: vi.fn(async () => ({ linked: 0, results: [] })),
  };
});

vi.mock('../../../_shared/services/orderInquiryReserveService', () => ({
  createOrderInquiryReserveRequest: vi.fn(async () => ({ id: 'rr-1', ordinal: 1 })),
  getOrderInquiryReserveRequests: vi.fn(async () => []),
}));

vi.mock('../../../_shared/components/RequestReserveDialog', () => ({
  RequestReserveDialog: ({ rows }: { rows: OrderInquiryWorklistRow[] }) => (
    <div data-testid="reserve-dialog-rows">{rows.map((row) => row.id).join(',')}</div>
  ),
}));

import { OrderInquiryDetail } from './OrderInquiryDetail';

function renderDetail() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <OrderInquiryDetail id="oi-1" />
    </QueryClientProvider>,
  );
}

async function requestFor(itemCode: string): Promise<string> {
  renderDetail();
  await screen.findAllByText(itemCode);
  fireEvent.click(await screen.findByLabelText(`Select ${itemCode}`));
  fireEvent.pointerDown(screen.getByRole('button', { name: 'Order inquiry options' }), {
    button: 0,
  });
  fireEvent.click(await screen.findByRole('menuitem', { name: /request cs to reserve/i }));
  return (await screen.findByTestId('reserve-dialog-rows')).textContent ?? '';
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('OI-RESERVE-ANY-ROW: the rows one ticked line sends to Request CS to reserve', () => {
  it('a line split over two ORDER rows sends both', async () => {
    expect(await requestFor('ZZT-SPLIT')).toBe('split-a,split-b');
  });

  it('a line whose ORDER and DELAY rows are both live sends one row, the ORDER', async () => {
    expect(await requestFor('ZZT-BOTH')).toBe('both-order');
  });

  it('OI-2609-0257 line 7: the DELAY row, its only live row, is sent', async () => {
    expect(await requestFor('ZZT-L7')).toBe('l7-delay');
  });
});
