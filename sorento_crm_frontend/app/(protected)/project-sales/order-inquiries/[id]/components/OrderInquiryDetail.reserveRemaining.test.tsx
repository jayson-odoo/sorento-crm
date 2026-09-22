/**
 * Reviewer fix round, BLOCKER B1 (`PLAN-oi-request-cs-reserve.md`): `OrderInquiryDetail
 * .tsx`'s own `reserveIneligibleReason` and `reserveDialogRows` both recompute "remaining"
 * as `qty - linked_qty - bundled_qty` - NEITHER subtracts `reserved_qty`. The backend's
 * own `links_for_rows` deliberately EXCLUDES a reserve-kind link from `linked_qty`
 * (`project_order_inquiry_service.py`: "a reserve link is not a PO or an SPO document...
 * `reserved_qty` is where it actually surfaces"), so a row already reserved 50 of 139
 * reads `remaining = 139`, not 89 - the dialog would let purchasing ask CS to reserve
 * MORE than is actually left, and a row reserved IN FULL (`reserved_qty == qty`) never
 * disables the "Request CS to reserve" menu item at all.
 *
 * `reserveIneligibleReason` / `reserveDialogRows` are neither exported - tested through
 * the RENDERED menu and dialog instead, the same harness `OrderInquiryDetail.test.tsx`
 * already uses (mocked services, ticked-row selection via the DataGrid's own checkbox).
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
    ...over,
  } as unknown as OrderInquiryWorklistRow;
}

const PARTIALLY_RESERVED = reserveRow({
  id: 'row-partial',
  item_code: 'ZZT-PARTIAL',
  qty: '139',
  reserved_qty: '50',
  reserve_state: 'reserved',
});

const FULLY_RESERVED = reserveRow({
  id: 'row-full',
  item_code: 'ZZT-FULL',
  qty: '139',
  reserved_qty: '139',
  reserve_state: 'reserved',
});

vi.mock('../../../_shared/services/orderInquiryService', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('../../../_shared/services/orderInquiryService')>();
  return {
    ...actual,
    getOrderInquiryHeader: vi.fn(async () => HEADER),
    getOrderInquiryHeaderLines: vi.fn(async () => [PARTIALLY_RESERVED, FULLY_RESERVED]),
    getOrderInquiryHeaderRelatedDocuments: vi.fn(async () => ({ purchase_orders: [], spos: [] })),
    listOrderInquiryHeaders: vi.fn(async () => ({ data: [], total: 0, page: 1, limit: 25 })),
    acknowledgeOrderInquiryRowsByFilter: vi.fn(async () => ({ acknowledged: 0, results: [] })),
    acknowledgeOrderInquiryRows: vi.fn(async () => ({ acknowledged: 0, results: [] })),
    autoPlaceOrderInquiryRows: vi.fn(async () => ({ linked: 0, results: [] })),
  };
});

vi.mock('../../../_shared/services/orderInquiryReserveService', () => ({
  createOrderInquiryReserveRequest: vi.fn(async () => ({
    id: 'rr-1', ordinal: 1, first_to_name: 'Eling',
  })),
  getOrderInquiryReserveRequests: vi.fn(async () => []),
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

function openGearMenu() {
  fireEvent.pointerDown(screen.getByRole('button', { name: 'Order inquiry options' }), {
    button: 0,
  });
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('BLOCKER B1: reserved_qty must count against remaining, not just linked_qty', () => {
  it('a row reserved 50 of 139 defaults Requested to 89, capped at 89', async () => {
    renderDetail();
    await screen.findByText('ZZT-PARTIAL');

    fireEvent.click(await screen.findByLabelText('Select ZZT-PARTIAL'));
    openGearMenu();
    fireEvent.click(await screen.findByRole('menuitem', { name: /request cs to reserve/i }));

    const requestedInput = (await screen.findByLabelText('Requested')) as HTMLInputElement;
    expect(requestedInput.value).toBe('89');
    expect(requestedInput.max).toBe('89');
  });

  it('a row reserved in full (139 of 139) is not requestable: menu disabled, nothing left to request', async () => {
    renderDetail();
    await screen.findByText('ZZT-FULL');

    fireEvent.click(await screen.findByLabelText('Select ZZT-FULL'));
    openGearMenu();

    const item = await screen.findByRole('menuitem', { name: /request cs to reserve/i });
    expect(item).toHaveAttribute('aria-disabled', 'true');
    expect(screen.getByText(/nothing left/i)).toBeInTheDocument();
  });
});
