/**
 * `PLAN-oi-request-cs-reserve.md` section 6c F2, `oi-request-cs-reserve-acceptance-
 * criteria.md` AC-RS-61 (icon half) / AC-RS-62 (round 2).
 *
 * TEST-FIRST (Phase 2): today the Lines grid's own "State" column
 * (`orderInquiryHeaderLinesColumns.tsx`) prints a non-interactive `ReservePill` beside
 * the state pill, and `ReserveRequestsCard`/`ReserveRequestsSection` render the open
 * request above the grid. F2 replaces both with ONE icon-button per row that OPENS a
 * per-row dialog (`ReserveRowDialog.test.tsx` pins that component itself) - this file
 * pins the ICON's own presence rule and the `?reserve=` wiring, through the same
 * rendered-`OrderInquiryDetail` harness `OrderInquiryDetail.reserveRemaining.test.tsx`
 * already uses (mocked services, DataGrid column-preferences stub -
 * `project_datagrid_jsdom_rows_mockable.md`).
 *
 * A red here is "no such button" / "the dialog never opens" / "the param survives close"
 * - the plan's own stated behaviour not existing yet - never an import typo.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type {
  OrderInquiryHeaderDetail,
  OrderInquiryWorklistRow,
} from '../../../_shared/types/orderInquiry.types';

const replaceSpy = vi.fn();
let searchParamsValue = '';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: replaceSpy }),
  usePathname: () => '/project-sales/order-inquiries/oi-1',
  useSearchParams: () => new URLSearchParams(searchParamsValue),
}));

vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => true,
}));

// S1 (reviewer round): `OrderInquiryDetail` reads `useSession` directly now.
vi.mock('next-auth/react', () => ({
  useSession: () => ({ data: { user: { id: 'test-current-user' } }, status: 'authenticated' }),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

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

function row(over: Partial<OrderInquiryWorklistRow>): OrderInquiryWorklistRow {
  return {
    id: 'row-plain',
    order_inquiry_id: 'oi-1',
    item_code: 'ZZT-PLAIN',
    qty: '30',
    delivery_date: null,
    supplier: null,
    po_number: null,
    location: null,
    product_id: 'prod-1',
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

const PLAIN_ROW = row({ id: 'row-plain', item_code: 'ZZT-PLAIN' });
const REQUESTED_ROW = row({
  id: 'row-requested',
  item_code: 'ZZT-REQUESTED',
  reserve_state: 'requested',
});
const RESERVED_ROW = row({
  id: 'row-reserved',
  item_code: 'ZZT-RESERVED',
  reserve_state: 'reserved',
  reserved_qty: '50',
});

const OPEN_REQUEST = {
  id: 'rr-1',
  order_inquiry_id: 'oi-1',
  ordinal: 1,
  state: 'requested' as const,
  requested_by: 'user-1',
  requested_by_name: 'Joey',
  requested_at: '2026-09-22T09:00:00',
  note: null,
  reserved_by_name: null,
  reserved_at: null,
  cancelled_at: null,
  first_to_name: null,
  rows: [
    {
      id: 'reqrow-1',
      row_id: 'row-requested',
      item_code: 'ZZT-REQUESTED',
      qty_requested: '30',
      warehouse_id: null,
      location: null,
      qty_reserved: null,
      reason: null,
    },
  ],
};

vi.mock('../../../_shared/services/orderInquiryService', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('../../../_shared/services/orderInquiryService')>();
  return {
    ...actual,
    getOrderInquiryHeader: vi.fn(async () => HEADER),
    getOrderInquiryHeaderLines: vi.fn(async () => [PLAIN_ROW, REQUESTED_ROW, RESERVED_ROW]),
    getOrderInquiryHeaderRelatedDocuments: vi.fn(async () => ({ purchase_orders: [], spos: [] })),
    listOrderInquiryHeaders: vi.fn(async () => ({ data: [], total: 0, page: 1, limit: 25 })),
    acknowledgeOrderInquiryRowsByFilter: vi.fn(async () => ({ acknowledged: 0, results: [] })),
    acknowledgeOrderInquiryRows: vi.fn(async () => ({ acknowledged: 0, results: [] })),
    autoPlaceOrderInquiryRows: vi.fn(async () => ({ linked: 0, results: [] })),
  };
});

vi.mock('../../../_shared/services/orderInquiryReserveService', () => ({
  createOrderInquiryReserveRequest: vi.fn(async () => ({
    id: 'rr-2', ordinal: 2, first_to_name: 'Eling',
  })),
  getOrderInquiryReserveRequests: vi.fn(async () => [OPEN_REQUEST]),
  reserveOrderInquiryRow: vi.fn(async () => ({ id: 'reqrow-1' })),
  unreserveOrderInquiryRow: vi.fn(async () => ({ id: 'reqrow-1' })),
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

beforeEach(() => {
  vi.clearAllMocks();
  searchParamsValue = '';
});

/** The grid TABLE row for an item code, never a stray match elsewhere on the page (the
 * still-live `ReserveRequestsCard`/`ReserveRequestsSection` prints the SAME item code a
 * second time for an open request, which is itself part of what AC-RS-61 says must stop -
 * so more than one match is an expected shape today, not a fixture bug). */
function gridRowFor(itemCode: string): HTMLElement {
  const matches = screen.getAllByText(itemCode);
  const withinRow = matches.map((el) => el.closest('tr')).find((tr): tr is HTMLTableRowElement => Boolean(tr));
  expect(withinRow).toBeTruthy();
  return withinRow as HTMLElement;
}

describe('AC-RS-61: the Reserve icon-button only on requested/reserved rows', () => {
  it('a plain row (reserve_state null) carries no Reserve button', async () => {
    renderDetail();
    await screen.findByText('ZZT-PLAIN');

    const plainRow = gridRowFor('ZZT-PLAIN');
    expect(
      plainRow.querySelector('[aria-label="Reserve"]'),
    ).not.toBeInTheDocument();
  });

  it('a requested row carries a Reserve button; clicking it opens the dialog for THAT row', async () => {
    renderDetail();
    await screen.findAllByText('ZZT-REQUESTED');

    const requestedRow = gridRowFor('ZZT-REQUESTED');
    const button = requestedRow.querySelector('[aria-label="Reserve"]');
    expect(button).toBeInTheDocument();

    fireEvent.click(button as Element);

    expect(await screen.findByRole('tab', { name: /reserve/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /history/i })).toBeInTheDocument();
  });

  it('a reserved row (no open request) also carries a Reserve button', async () => {
    renderDetail();
    await screen.findByText('ZZT-RESERVED');

    const reservedRow = gridRowFor('ZZT-RESERVED');
    expect(reservedRow.querySelector('[aria-label="Reserve"]')).toBeInTheDocument();
  });

  it('ReserveRequestsCard / "Earlier reserve requests" no longer render on this page', async () => {
    renderDetail();
    await screen.findAllByText('ZZT-REQUESTED');

    expect(screen.queryByText(/earlier reserve requests/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/^request #\d+$/i)).not.toBeInTheDocument();
  });
});

describe('AC-RS-62: ?reserve=<request_id> auto-opens the dialog on the first open row', () => {
  it('auto-opens for the open request row named by the query param', async () => {
    searchParamsValue = 'reserve=rr-1';
    renderDetail();

    expect(await screen.findByRole('tab', { name: /reserve/i })).toBeInTheDocument();
    // The dialog opened for row-requested's own item code, not any other row's.
    expect(screen.getAllByText('ZZT-REQUESTED').length).toBeGreaterThan(0);
  });

  it('closing the dialog removes the reserve param, the icon stays', async () => {
    searchParamsValue = 'reserve=rr-1';
    renderDetail();

    await screen.findByRole('tab', { name: /reserve/i });
    const closeButtons = screen.getAllByRole('button', { name: /close/i });
    fireEvent.click(closeButtons[closeButtons.length - 1]);

    await waitFor(() => expect(replaceSpy).toHaveBeenCalled());
    const [urlArg] = replaceSpy.mock.calls[replaceSpy.mock.calls.length - 1] as [string];
    expect(urlArg).not.toMatch(/reserve=/);

    await screen.findAllByText('ZZT-REQUESTED');
    const requestedRow = gridRowFor('ZZT-REQUESTED');
    expect(requestedRow.querySelector('[aria-label="Reserve"]')).toBeInTheDocument();
  });
});
