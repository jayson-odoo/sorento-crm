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

// F2 (fix round 3 review finding): a per-permission override, so a single test can
// simulate a requester who holds `acknowledge` (can raise a request) but not
// `reserve` (cannot confirm one) - every OTHER test leaves this `null` and gets the
// old blanket `true`.
let reservePermissionOverride: boolean | null = null;
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (permission: string) =>
    permission === 'projects.order_inquiries.reserve' && reservePermissionOverride !== null
      ? reservePermissionOverride
      : true,
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

// Nits (fix round 2): asserted directly - the requestedByName / completes toast
// wording (AC-RS-56) is otherwise invisible to this suite.
const toastSuccessSpy = vi.fn();
vi.mock('@/lib/toast', () => ({
  toast: {
    success: (...args: unknown[]) => toastSuccessSpy(...args),
    error: vi.fn(),
    warning: vi.fn(),
    dismiss: vi.fn(),
  },
}));

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

const getReserveRequestsMock = vi.fn(async () => [OPEN_REQUEST]);
vi.mock('../../../_shared/services/orderInquiryReserveService', () => ({
  createOrderInquiryReserveRequest: vi.fn(async () => ({
    id: 'rr-2', ordinal: 2, first_to_name: 'Eling',
  })),
  getOrderInquiryReserveRequests: (...args: unknown[]) =>
    getReserveRequestsMock(...(args as [string])),
  reserveOrderInquiryRow: vi.fn(async () => ({ id: 'reqrow-1' })),
  unreserveOrderInquiryRow: vi.fn(async () => ({ id: 'reqrow-1' })),
}));

// Re-review finding 1 (captain ruling, 23 Sep): `unreserveControl.start` parks a
// deferred action - mocked here (not exercised in the rest of this file) so the
// anchor test below can assert the exact `request_id` it parks with.
const createPendingActionSpy = vi.fn(async ({ entityId }: { entityId: string }) => ({
  id: `pa-${entityId}`,
  action_key: 'order_inquiry_reserve_row.unreserve',
  entity_type: 'order_inquiry_reserve_row',
  entity_id: entityId,
  commit_at: new Date(Date.now() + 10_000).toISOString(),
  window_seconds: 10,
}));
vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: (...args: unknown[]) =>
    createPendingActionSpy(...(args as [{ entityId: string }])),
  cancelPendingAction: vi.fn(async () => undefined),
  getCurrentPendingAction: vi.fn(async () => ({ pending: null, last_outcome: null })),
}));

// Fix round 1 (`PLAN-oi-request-cs-reserve.md` 6d "Fix round 1", AC-RS-65b):
// `useReserveRowOptions` reads this per PRODUCT - two rows naming different products
// must resolve two different pool lists, not one shared by the whole dialog.
const getStockDetailMock = vi.fn(async (productId: string) => {
  if (productId === 'prod-a') {
    return { locations: [{ warehouse_id: 'wh-a', location: 'BRW', available_qty: '12' }] };
  }
  if (productId === 'prod-b') {
    return { locations: [{ warehouse_id: 'wh-b', location: 'DC1', available_qty: '7' }] };
  }
  return { locations: [] };
});
vi.mock('../../../_shared/services/fulfilmentPlanningService', () => ({
  getStockDetail: (...args: unknown[]) => getStockDetailMock(...(args as [string])),
}));

import { OrderInquiryDetail } from './OrderInquiryDetail';
// Round 3 (`PLAN-oi-request-cs-reserve.md` section 6d G1, AC-RS-65): overrides the
// module-level mock's resolved lines per test, the same way `getReserveRequestsMock`
// already does for the reserve-requests read.
import { getOrderInquiryHeaderLines } from '../../../_shared/services/orderInquiryService';
// Nits (fix round 2): the query key a forced `invalidateQueries` targets, in the
// "reads the requester off the REQUEST" test.
import { ORDER_INQUIRY_RESERVE_REQUESTS_KEY } from '../../../_shared/hooks/useOrderInquiry';

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
  reservePermissionOverride = null;
  getReserveRequestsMock.mockResolvedValue([OPEN_REQUEST]);
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

/**
 * S5 (`PLAN-oi-request-cs-reserve.md` section 6d, fix round 2 review finding). Today
 * `router.replace` dropping `?reserve=` off the URL is async (a real `next/navigation`
 * round trip) - `searchParamsValue`/`replaceSpy` here stand in for that lag exactly:
 * `replaceSpy` is a no-op mock, so the module-level `searchParamsValue` string this
 * suite's own `useSearchParams` mock reads from never actually changes on Close. A
 * reserve-requests refetch landing (or any other re-render) after Close therefore
 * still sees `?reserve=rr-1` AND the row it names still open - without a latch on the
 * ALREADY-HANDLED param, the effect that auto-opens the dialog fires again and
 * reopens the very dialog Close just closed.
 *
 * TEST-FIRST (fix round 2): today closing does not remember the param it just
 * handled - a red here is "the Reserve tab is back after a rerender with the exact
 * same search params", never a fixture bug.
 */
describe('S5 (fix round 2): closing latches against a stale refetch reopening the dialog', () => {
  it('close, then a rerender with the SAME search params + refetched data - the dialog stays closed', async () => {
    searchParamsValue = 'reserve=rr-1';
    const { rerender } = renderDetail();

    await screen.findByRole('tab', { name: /reserve/i });
    const closeButtons = screen.getAllByRole('button', { name: /close/i });
    fireEvent.click(closeButtons[closeButtons.length - 1]);

    await waitFor(() => expect(replaceSpy).toHaveBeenCalled());
    await waitFor(() =>
      expect(screen.queryByRole('tab', { name: /reserve/i })).not.toBeInTheDocument(),
    );

    // The "refetch" - a fresh resolved value off the SAME mock, `searchParamsValue`
    // deliberately left untouched (the async URL update this test stands in for has
    // not landed yet either).
    getReserveRequestsMock.mockResolvedValue([{ ...OPEN_REQUEST }]);

    // Import (a fresh `QueryClientProvider` tree, same `id`) so `useSearchParams()`
    // is called again and the effect's own dependency array sees a NEW object - the
    // exact shape a real re-render carries in this mocked environment (every call to
    // the mock returns a new `URLSearchParams` instance).
    rerender(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <OrderInquiryDetail id="oi-1" />
      </QueryClientProvider>,
    );

    await screen.findAllByText('ZZT-REQUESTED');
    expect(screen.queryByRole('tab', { name: /reserve/i })).not.toBeInTheDocument();
  });
});

describe('Re-review finding 1 (captain ruling, 23 Sep): Unreserve is reachable and anchored on the request that still holds the link', () => {
  const REQUEST_WITH_LINK = {
    id: 'rr-with-link',
    order_inquiry_id: 'oi-1',
    ordinal: 1,
    state: 'reserved' as const,
    requested_by: 'user-1',
    requested_by_name: 'Joey',
    requested_at: '2026-09-20T09:00:00',
    note: null,
    reserved_by_name: 'Eling',
    reserved_at: '2026-09-20T10:00:00',
    cancelled_at: null,
    first_to_name: null,
    rows: [
      {
        id: 'reqrow-with-link',
        row_id: 'row-reserved',
        item_code: 'ZZT-RESERVED',
        qty_requested: '50',
        warehouse_id: 'wh-1',
        location: 'BRW',
        qty_reserved: '50',
        reason: null,
      },
    ],
  };
  const REQUEST_ANSWERED_ZERO = {
    id: 'rr-answered-zero',
    order_inquiry_id: 'oi-1',
    ordinal: 2,
    state: 'reserved' as const,
    requested_by: 'user-1',
    requested_by_name: 'Joey',
    requested_at: '2026-09-21T09:00:00',
    note: null,
    reserved_by_name: 'Eling',
    reserved_at: '2026-09-21T10:00:00',
    cancelled_at: null,
    first_to_name: null,
    rows: [
      {
        id: 'reqrow-zero',
        row_id: 'row-reserved',
        item_code: 'ZZT-RESERVED',
        qty_requested: '10',
        warehouse_id: null,
        location: null,
        qty_reserved: '0',
        reason: 'nothing left',
      },
    ],
  };

  it('is reachable via Unreserve even when the highest-ordinal request was answered 0, and parks against the request that still holds the reserve', async () => {
    getReserveRequestsMock.mockResolvedValue([REQUEST_WITH_LINK, REQUEST_ANSWERED_ZERO]);

    renderDetail();
    await screen.findByText('ZZT-RESERVED');

    const reservedRow = gridRowFor('ZZT-RESERVED');
    fireEvent.click(reservedRow.querySelector('[aria-label="Reserve"]') as Element);

    await screen.findByRole('tab', { name: /reserve/i });
    fireEvent.click(await screen.findByRole('button', { name: /^unreserve$/i }));
    fireEvent.change(await screen.findByLabelText(/qty/i), { target: { value: '10' } });
    fireEvent.click(screen.getByRole('button', { name: /^unreserve$/i }));

    await waitFor(() => expect(createPendingActionSpy).toHaveBeenCalledTimes(1));
    const [call] = createPendingActionSpy.mock.calls[0] as [{ payload: { request_id: string } }];
    expect(call.payload.request_id).toBe('rr-with-link');
  });
});

/**
 * Round 3 (`PLAN-oi-request-cs-reserve.md` section 6d G1, AC-RS-65). Supersedes the
 * "first open row" clause of AC-RS-62 above: `?reserve=<request_id>` used to open the
 * dialog for the request's FIRST open row alone - now it opens ONE dialog carrying a
 * section for EVERY still-open row of that request, and drops the History tab (which
 * belongs to the single-row, line-click path - AC-RS-67 pins that half in
 * `ReserveRowDialog.test.tsx`).
 */
describe('AC-RS-65: ?reserve=<request_id> opens ONE dialog with a section per still-open row', () => {
  const ROW_A = row({ id: 'row-a', item_code: 'ZZT-ROWA', reserve_state: 'requested' });
  const ROW_B = row({ id: 'row-b', item_code: 'ZZT-ROWB', reserve_state: 'requested' });
  const ROW_C = row({
    id: 'row-c',
    item_code: 'ZZT-ROWC',
    reserve_state: 'reserved',
    reserved_qty: '10',
  });

  /** One request, three rows: two still open, one already answered within it. */
  const MULTI_ROW_REQUEST = {
    id: 'rr-multi',
    order_inquiry_id: 'oi-1',
    ordinal: 3,
    state: 'requested' as const,
    requested_by: 'user-1',
    requested_by_name: 'Joey',
    requested_at: '2026-09-23T09:00:00',
    note: null,
    reserved_by_name: null,
    reserved_at: null,
    cancelled_at: null,
    first_to_name: null,
    rows: [
      {
        id: 'reqrow-a',
        row_id: 'row-a',
        item_code: 'ZZT-ROWA',
        qty_requested: '20',
        warehouse_id: null,
        location: null,
        qty_reserved: null,
        reason: null,
      },
      {
        id: 'reqrow-b',
        row_id: 'row-b',
        item_code: 'ZZT-ROWB',
        qty_requested: '15',
        warehouse_id: null,
        location: null,
        qty_reserved: null,
        reason: null,
      },
      {
        id: 'reqrow-c',
        row_id: 'row-c',
        item_code: 'ZZT-ROWC',
        qty_requested: '10',
        warehouse_id: null,
        location: null,
        qty_reserved: '10',
        reason: null,
      },
    ],
  };

  it('two open rows + one already-reserved row: one dialog, two Confirm sections, no History tab', async () => {
    vi.mocked(getOrderInquiryHeaderLines).mockResolvedValue([PLAIN_ROW, ROW_A, ROW_B, ROW_C]);
    getReserveRequestsMock.mockResolvedValue([MULTI_ROW_REQUEST]);
    searchParamsValue = 'reserve=rr-multi';

    renderDetail();

    // ONE dialog only - never one per open row.
    await waitFor(() => expect(screen.getAllByRole('dialog')).toHaveLength(1));

    // Today the deep link opens a dialog for the FIRST open row alone, so only ONE
    // "Confirm reserved" renders here - this is where the red sits.
    expect(await screen.findAllByRole('button', { name: /confirm reserved/i })).toHaveLength(2);

    // Round 3 supersedes the single-row dialog's own History tab for this path - it
    // lives on the line now (`ReserveRowDialog.test.tsx` AC-RS-67), never inside a
    // multi-row deep link.
    expect(screen.queryByRole('tab', { name: /history/i })).not.toBeInTheDocument();
  });

  /**
   * Nits (fix round 2, AC-RS-56). Two, exercised together because the second only
   * shows up once the first row is answered:
   *
   * 1. The toast reads plain "Reserved" on a non-final confirm, and "Reserved, <name>
   *    notified" only on the confirm that COMPLETES the request (every carried row
   *    now confirmed, tracked client-side) - the mail itself dispatches server-side
   *    on completion; this only decides what the toast claims.
   * 2. `requestedByName` is resolved off the REQUEST `onReserve` is actually called
   *    for, not the PRIMARY row's own `openRequest` - which goes null the moment
   *    that row itself is answered (its own request-row entry no longer carries
   *    `qty_reserved: null`), leaving the LAST section's own confirm with no name to
   *    read under the old code.
   *
   * TEST-FIRST (fix round 2): today the first confirm's own toast already reads
   * "Reserved, Joey notified" (no `completes` gate) - a red on the FIRST assertion.
   * After that fix lands, the second (final) confirm's toast reads "Reserved, the
   * requester notified" once row-a's own request-row entry is answered in the
   * refetched data - a red on the SECOND assertion, never a fixture bug.
   */
  it('nits: toast completes only once, and reads the requester off the REQUEST even after the primary row is answered', async () => {
    vi.mocked(getOrderInquiryHeaderLines).mockResolvedValue([PLAIN_ROW, ROW_A, ROW_B]);
    getReserveRequestsMock.mockResolvedValue([MULTI_ROW_REQUEST]);
    searchParamsValue = 'reserve=rr-multi';

    // A LOCAL client (rather than the shared `renderDetail` helper) so the test can
    // force the SAME `invalidateQueries` a real confirm triggers and await it
    // settling BEFORE the second click - `reserveRequestsQuery.data` otherwise never
    // actually reflects row-a's own answer in time for the assertion below to mean
    // anything.
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    render(
      <QueryClientProvider client={client}>
        <OrderInquiryDetail id="oi-1" />
      </QueryClientProvider>,
    );

    const confirmButtons = await screen.findAllByRole('button', { name: /confirm reserved/i });
    expect(confirmButtons).toHaveLength(2);

    fireEvent.click(confirmButtons[0]);
    await waitFor(() => expect(toastSuccessSpy).toHaveBeenCalledTimes(1));
    expect(toastSuccessSpy).toHaveBeenNthCalledWith(1, 'Reserved');

    // The refetch a real confirm triggers (`invalidateQueries`) - row-a (the
    // PRIMARY row, first in `reserveDialogRowIds`) is now answered, row-b stays
    // open. `openRequestForRow('row-a')` - and so the OLD primary-row-derived
    // `requestedByName` - can no longer find this request once this lands.
    getReserveRequestsMock.mockResolvedValue([
      {
        ...MULTI_ROW_REQUEST,
        rows: [
          { ...MULTI_ROW_REQUEST.rows[0], qty_reserved: '20' },
          MULTI_ROW_REQUEST.rows[1],
        ],
      },
    ]);
    await client.invalidateQueries({ queryKey: [ORDER_INQUIRY_RESERVE_REQUESTS_KEY, 'oi-1'] });
    // Waits for the QUERY CACHE itself to carry the updated shape, rather than a
    // call count - `invalidateQueries` after the first confirm's own `onSuccess`
    // already triggered one refetch before this explicit one lands.
    await waitFor(() => {
      const cached = client.getQueryData([ORDER_INQUIRY_RESERVE_REQUESTS_KEY, 'oi-1']) as
        | Array<{ rows: Array<{ row_id: string; qty_reserved: string | null }> }>
        | undefined;
      const rowA = cached?.[0]?.rows.find((r) => r.row_id === 'row-a');
      expect(rowA?.qty_reserved).toBe('20');
    });

    await waitFor(() =>
      expect(screen.getAllByRole('button', { name: /confirm reserved/i })).toHaveLength(1),
    );

    fireEvent.click(screen.getByRole('button', { name: /confirm reserved/i }));
    await waitFor(() => expect(toastSuccessSpy).toHaveBeenCalledTimes(2));
    expect(toastSuccessSpy).toHaveBeenNthCalledWith(2, 'Reserved, Joey notified');
  });
});

/**
 * Fix round 1 (`PLAN-oi-request-cs-reserve.md` 6d "Fix round 1", `oi-request-cs-
 * reserve-acceptance-criteria.md` AC-RS-65b). TEST-FIRST: today `OrderInquiryDetail`
 * resolves `useReserveRowOptions` for the PRIMARY row alone and hands that ONE result
 * to every section of the dialog - two rows naming different products both end up
 * offered the primary row's own pools. A red here is "getStockDetail was called for
 * only one product" / "the second section shows the first row's own pool options" -
 * never a fixture bug.
 */
describe('AC-RS-65b: a multi-row dialog resolves pool options PER ROW, off each row\'s own product', () => {
  const ROW_PROD_A = row({
    id: 'row-prod-a',
    item_code: 'PRODA-1',
    product_id: 'prod-a',
    reserve_state: 'requested',
  });
  const ROW_PROD_B = row({
    id: 'row-prod-b',
    item_code: 'PRODB-1',
    product_id: 'prod-b',
    reserve_state: 'requested',
  });
  const MULTI_PRODUCT_REQUEST = {
    id: 'rr-multi-product',
    order_inquiry_id: 'oi-1',
    ordinal: 5,
    state: 'requested' as const,
    requested_by: 'user-1',
    requested_by_name: 'Joey',
    requested_at: '2026-09-23T09:00:00',
    note: null,
    reserved_by_name: null,
    reserved_at: null,
    cancelled_at: null,
    first_to_name: null,
    rows: [
      {
        id: 'reqrow-prod-a',
        row_id: 'row-prod-a',
        item_code: 'PRODA-1',
        qty_requested: '10',
        warehouse_id: null,
        location: null,
        qty_reserved: null,
        reason: null,
      },
      {
        id: 'reqrow-prod-b',
        row_id: 'row-prod-b',
        item_code: 'PRODB-1',
        qty_requested: '5',
        warehouse_id: null,
        location: null,
        qty_reserved: null,
        reason: null,
      },
    ],
  };

  it('resolves getStockDetail once per distinct product, and each section shows only its own product\'s pools', async () => {
    vi.mocked(getOrderInquiryHeaderLines).mockResolvedValue([PLAIN_ROW, ROW_PROD_A, ROW_PROD_B]);
    getReserveRequestsMock.mockResolvedValue([MULTI_PRODUCT_REQUEST]);
    searchParamsValue = 'reserve=rr-multi-product';

    renderDetail();

    await waitFor(() => expect(screen.getAllByRole('dialog')).toHaveLength(1));
    await waitFor(() => expect(getStockDetailMock).toHaveBeenCalledWith('prod-a', null, [], 'pools'));
    await waitFor(() => expect(getStockDetailMock).toHaveBeenCalledWith('prod-b', null, [], 'pools'));
    // Every product resolved is one of the two the dialog's rows actually name - never
    // the primary row's own product asked twice, never a third, unrelated one.
    const productsAsked = new Set(getStockDetailMock.mock.calls.map((call) => call[0]));
    expect(productsAsked).toEqual(new Set(['prod-a', 'prod-b']));

    // Reserved default is min(requested, THIS product's own available qty) - 10 for
    // prod-a (min(10, 12)), 5 for prod-b (min(5, 7)).
    const reservedInputs = await screen.findAllByLabelText('Reserved');
    expect(reservedInputs).toHaveLength(2);
    expect((reservedInputs[0] as HTMLInputElement).value).toBe('10');
    expect((reservedInputs[1] as HTMLInputElement).value).toBe('5');

    // The first section's own Location dropdown offers prod-a's own pool (BRW) only -
    // never prod-b's DC1, which would mean the primary row's resolution leaked across.
    // Scoped to `role=option` (the opened listbox's own entries), because the SECOND
    // section's own selected value already renders the text "DC1" too.
    const locationSelects = screen.getAllByLabelText('Location');
    fireEvent.click(locationSelects[0]);
    const options = await screen.findAllByRole('option');
    expect(options.map((option) => option.textContent)).toEqual(
      expect.arrayContaining([expect.stringContaining('BRW')]),
    );
    expect(options.some((option) => (option.textContent ?? '').includes('DC1'))).toBe(false);
  });
});

/**
 * F1 (`PLAN-oi-request-cs-reserve.md` section 6d, fix round 3 review finding). The
 * round-2 "completes" counter (`reserveConfirmedRowIdsRef.current.size + 1 >=
 * reserveRowDialogRows.length`) read wrong on every axis a SINGLE-ROW dialog exposes:
 * `reserveRowDialogRows.length` is the DIALOG's own row count (1, for a line-click
 * dialog), not the REQUEST's - so a single-row confirm always counted as "completing"
 * even while the SAME request's other rows (never carried by this dialog at all)
 * stayed open. The fix reads the REQUEST's own full `rows` list off
 * `reserveRequestsQuery.data` at the moment `onReserve` is called, server truth
 * regardless of who answered what or when.
 *
 * TEST-FIRST (fix round 3): today EVERY one of these three confirms (single-row
 * dialogs, in a request naming rows never carried by the dialog itself) reads
 * "Reserved, Joey notified" - a red here is exactly that wording where "Reserved"
 * alone (or vice versa) is correct, never a fixture bug.
 */
describe('F1 (fix round 3): completes is SERVER TRUTH off the request, not a dialog-row counter', () => {
  const ROW_X = row({ id: 'row-x', item_code: 'ZZT-X', reserve_state: 'requested' });

  function requestFixture(rowsOverride: Array<Record<string, unknown>>) {
    return {
      id: 'rr-f1',
      order_inquiry_id: 'oi-1',
      ordinal: 5,
      state: 'requested' as const,
      requested_by: 'user-1',
      requested_by_name: 'Joey',
      requested_at: '2026-09-23T09:00:00',
      note: null,
      reserved_by_name: null,
      reserved_at: null,
      cancelled_at: null,
      first_to_name: null,
      rows: rowsOverride,
    };
  }

  async function openAndConfirmRowX() {
    renderDetail();
    await screen.findByText('ZZT-X');
    const rowXGrid = gridRowFor('ZZT-X');
    fireEvent.click(rowXGrid.querySelector('[aria-label="Reserve"]') as Element);

    const confirmButton = await screen.findByRole('button', { name: /confirm reserved/i });
    fireEvent.click(confirmButton);
    await waitFor(() => expect(toastSuccessSpy).toHaveBeenCalledTimes(1));
  }

  it('3-row open request, confirming ONE row: toast reads plain "Reserved" - the other two rows (never carried by this dialog) stay open', async () => {
    vi.mocked(getOrderInquiryHeaderLines).mockResolvedValue([PLAIN_ROW, ROW_X]);
    getReserveRequestsMock.mockResolvedValue([
      requestFixture([
        { id: 'rr-x', row_id: 'row-x', item_code: 'ZZT-X', qty_requested: '10', warehouse_id: null, location: null, qty_reserved: null, reason: null },
        { id: 'rr-y', row_id: 'row-y', item_code: 'ZZT-Y', qty_requested: '5', warehouse_id: null, location: null, qty_reserved: null, reason: null },
        { id: 'rr-z', row_id: 'row-z', item_code: 'ZZT-Z', qty_requested: '8', warehouse_id: null, location: null, qty_reserved: null, reason: null },
      ]),
    ]);

    await openAndConfirmRowX();

    expect(toastSuccessSpy).toHaveBeenCalledWith('Reserved');
  });

  it('the LAST open row of a 3-row request: toast reads "Reserved, <name> notified"', async () => {
    vi.mocked(getOrderInquiryHeaderLines).mockResolvedValue([PLAIN_ROW, ROW_X]);
    getReserveRequestsMock.mockResolvedValue([
      requestFixture([
        { id: 'rr-x', row_id: 'row-x', item_code: 'ZZT-X', qty_requested: '10', warehouse_id: null, location: null, qty_reserved: null, reason: null },
        { id: 'rr-y', row_id: 'row-y', item_code: 'ZZT-Y', qty_requested: '5', warehouse_id: null, location: null, qty_reserved: '5', reason: null },
        { id: 'rr-z', row_id: 'row-z', item_code: 'ZZT-Z', qty_requested: '8', warehouse_id: null, location: null, qty_reserved: '8', reason: null },
      ]),
    ]);

    await openAndConfirmRowX();

    expect(toastSuccessSpy).toHaveBeenCalledWith('Reserved, Joey notified');
  });

  it('one row already answered SERVER-SIDE by someone else, confirming the other: notified', async () => {
    vi.mocked(getOrderInquiryHeaderLines).mockResolvedValue([PLAIN_ROW, ROW_X]);
    getReserveRequestsMock.mockResolvedValue([
      requestFixture([
        { id: 'rr-x', row_id: 'row-x', item_code: 'ZZT-X', qty_requested: '10', warehouse_id: null, location: null, qty_reserved: null, reason: null },
        // Answered by a DIFFERENT session/user entirely - this test never confirms it.
        { id: 'rr-w', row_id: 'row-w', item_code: 'ZZT-W', qty_requested: '3', warehouse_id: null, location: null, qty_reserved: '3', reason: null },
      ]),
    ]);

    await openAndConfirmRowX();

    expect(toastSuccessSpy).toHaveBeenCalledWith('Reserved, Joey notified');
  });
});

/**
 * F2 (fix round 3 review finding). `cancelControl` used to resolve `requestedBy` off
 * the PRIMARY row's own open request (`reserveRowOpenRequest`) - once the primary row
 * itself was answered (by anyone, at any time - here, someone else entirely, off this
 * session), that lookup went null even while ANOTHER row the SAME multi-row dialog
 * still carries stayed open, so `canCancelReserveRequest` was handed `undefined` and
 * "Cancel request" silently disappeared from a dialog that still had an open request
 * to cancel. The fix resolves `requestedBy` off `reserveDialogOpenRequest` - ANY
 * carried row still open, same identity across all of them since they share one
 * request.
 *
 * TEST-FIRST (fix round 3): today "Cancel request" disappears the moment row-1 (the
 * PRIMARY, first-listed row) is answered - a red here is "no such button" once that
 * lands, never a fixture bug.
 */
describe('F2 (fix round 3): Cancel request survives the PRIMARY row being answered first, for the requester without the reserve permission', () => {
  const ROW_CANCEL_A = row({ id: 'row-cancel-a', item_code: 'ZZT-CANCEL-A', reserve_state: 'requested' });
  const ROW_CANCEL_B = row({ id: 'row-cancel-b', item_code: 'ZZT-CANCEL-B', reserve_state: 'requested' });

  function twoRowRequest(rowARowReserved: string | null) {
    return {
      id: 'rr-cancel',
      order_inquiry_id: 'oi-1',
      ordinal: 6,
      state: 'requested' as const,
      // The CURRENT test user IS the requester - `canCancelReserveRequest` grants
      // Cancel to them even without the reserve permission (S1,
      // `orderInquiryReserve.ts`).
      requested_by: 'test-current-user',
      requested_by_name: 'Teh Jayson',
      requested_at: '2026-09-23T09:00:00',
      note: null,
      reserved_by_name: null,
      reserved_at: null,
      cancelled_at: null,
      first_to_name: null,
      rows: [
        {
          id: 'reqrow-cancel-a',
          row_id: 'row-cancel-a',
          item_code: 'ZZT-CANCEL-A',
          qty_requested: '10',
          warehouse_id: null,
          location: null,
          qty_reserved: rowARowReserved,
          reason: null,
        },
        {
          id: 'reqrow-cancel-b',
          row_id: 'row-cancel-b',
          item_code: 'ZZT-CANCEL-B',
          qty_requested: '5',
          warehouse_id: null,
          location: null,
          qty_reserved: null,
          reason: null,
        },
      ],
    };
  }

  it('Cancel request stays visible after row-cancel-a (primary) is answered by someone else, row-cancel-b still open', async () => {
    reservePermissionOverride = false;
    vi.mocked(getOrderInquiryHeaderLines).mockResolvedValue([PLAIN_ROW, ROW_CANCEL_A, ROW_CANCEL_B]);
    getReserveRequestsMock.mockResolvedValue([twoRowRequest(null)]);
    searchParamsValue = 'reserve=rr-cancel';

    const client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    render(
      <QueryClientProvider client={client}>
        <OrderInquiryDetail id="oi-1" />
      </QueryClientProvider>,
    );

    // Both rows open, no reserve permission - read-only sections (F2), no Confirm
    // reserved anywhere, but the requester's own Cancel request is offered.
    await waitFor(() => expect(screen.getAllByRole('dialog')).toHaveLength(1));
    expect((await screen.findAllByText('ZZT-CANCEL-A')).length).toBeGreaterThan(0);
    expect(screen.getAllByText('ZZT-CANCEL-B').length).toBeGreaterThan(0);
    expect(screen.queryByRole('button', { name: /confirm reserved/i })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /cancel request/i })).toBeInTheDocument();

    // row-cancel-a (the PRIMARY row) gets answered off this session entirely.
    getReserveRequestsMock.mockResolvedValue([twoRowRequest('10')]);
    await client.invalidateQueries({ queryKey: [ORDER_INQUIRY_RESERVE_REQUESTS_KEY, 'oi-1'] });
    await waitFor(() => {
      const cached = client.getQueryData([ORDER_INQUIRY_RESERVE_REQUESTS_KEY, 'oi-1']) as
        | Array<{ rows: Array<{ row_id: string; qty_reserved: string | null }> }>
        | undefined;
      const rowA = cached?.[0]?.rows.find((r) => r.row_id === 'row-cancel-a');
      expect(rowA?.qty_reserved).toBe('10');
    });

    // row-cancel-b is still open - Cancel request must still be offered.
    expect(screen.getByRole('button', { name: /cancel request/i })).toBeInTheDocument();
  });
});
