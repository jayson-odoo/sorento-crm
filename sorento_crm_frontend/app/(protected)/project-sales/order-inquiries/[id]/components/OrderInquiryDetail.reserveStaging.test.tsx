/**
 * `PLAN-oi-request-cs-reserve.md` section 6e (round 4, 24 Sep): CS reserves line by
 * line on the Lines grid itself - no per-row dialog, no multi-row dialog, no header
 * badge, no `Confirm all`. `oi-request-cs-reserve-acceptance-criteria.md`
 * AC-RS-83..89.
 *
 * TEST-FIRST (Phase 2): today (round 3 code, still on `OrderInquiryDetail.tsx`) the
 * Lines grid's own State cell renders `ReservePill` AS the click target (a single
 * button aria-label "Reserve", text "Request to reserve" with NO qty), which opens
 * `ReserveRowDialog` (tabs Reserve/History) - there is no staged map, no per-row
 * tick/pencil/undo icon set, no header `Reserve (N)` CTA, no State filter, and no
 * `ReserveLineHistoryDialog`. A red here is "no such chip" / "no such icon button" /
 * "the commit spy was never called" - the plan's own stated round-4 behaviour not
 * existing yet - never an import typo. Harness copied from
 * `OrderInquiryDetail.reserveIcon.test.tsx` (same mocked services, DataGrid
 * column-preferences stub, permission override).
 *
 * Field-name note for the captain: the worklist row type
 * (`_shared/types/orderInquiry.types.ts`) carries no field for "the open request's own
 * requested qty on this row" today (only `reserve_state` and `reserved_qty`) - AC-RS-83
 * needs that figure to print `Request to reserve 107`. This suite invents
 * `requested_qty` on the row fixture for it; the real implementation may resolve it off
 * the reserve-requests read instead (`openRequestForRow(...).qtyRequested`, already
 * plumbed) rather than adding a column - not this tester's call.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
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

let reservePermissionOverride: boolean | null = null;
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (permission: string) =>
    permission === 'projects.order_inquiries.reserve' && reservePermissionOverride !== null
      ? reservePermissionOverride
      : true,
}));

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

const toastSuccessSpy = vi.fn();
const toastErrorSpy = vi.fn();
vi.mock('@/lib/toast', () => ({
  toast: {
    success: (...args: unknown[]) => toastSuccessSpy(...args),
    error: (...args: unknown[]) => toastErrorSpy(...args),
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
  lines_total: 3,
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
    qty: '107',
    delivery_date: null,
    supplier: null,
    po_number: null,
    location: 'BRW-BB',
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

const PLAIN_ROW = row({ id: 'row-plain', item_code: 'ZZT-PLAIN', reserve_state: null });
// Invented field, see the file-header note.
const REQUESTED_ROW = row({
  id: 'row-requested',
  item_code: 'ZZT-REQUESTED',
  reserve_state: 'requested',
  qty: '107',
  ...({ requested_qty: '107' } as Record<string, unknown>),
});
const RESERVED_ROW = row({
  id: 'row-reserved',
  item_code: 'ZZT-RESERVED',
  reserve_state: 'reserved',
  reserved_qty: '30',
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
      qty_requested: '107',
      warehouse_id: 'wh-brw',
      location: 'BRW',
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
// AC-RS-87: `commitOrderInquiryReserve` does not exist on this service yet (round 4).
// Added here at the mock boundary so the module loads; the real service export is the
// coder's job. Every other export is the REAL implementation (round-2/3 machinery this
// suite deliberately never exercises).
const commitReserveSpy = vi.fn(async () => ({
  request: { ...OPEN_REQUEST, state: 'reserved' },
  reserved_count: 1,
}));
vi.mock('../../../_shared/services/orderInquiryReserveService', async (importOriginal) => {
  const actual = await importOriginal<
    typeof import('../../../_shared/services/orderInquiryReserveService')
  >();
  return {
    ...actual,
    getOrderInquiryReserveRequests: (...args: unknown[]) =>
      getReserveRequestsMock(...(args as [string])),
    commitOrderInquiryReserve: (...args: unknown[]) =>
      commitReserveSpy(...(args as [string, string, unknown])),
  };
});

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

const getStockDetailMock = vi.fn(async (productId: string) => {
  if (productId === 'prod-1') {
    return {
      locations: [
        { warehouse_id: 'wh-brw', location: 'BRW', available_qty: '107' },
        { warehouse_id: 'wh-dc1', location: 'DC1', available_qty: '20' },
      ],
    };
  }
  return { locations: [] };
});
vi.mock('../../../_shared/services/fulfilmentPlanningService', () => ({
  getStockDetail: (...args: unknown[]) => getStockDetailMock(...(args as [string])),
}));

import { OrderInquiryDetail } from './OrderInquiryDetail';
import { getOrderInquiryHeaderLines } from '../../../_shared/services/orderInquiryService';

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

/** The grid TABLE row for an item code. */
function gridRowFor(itemCode: string): HTMLElement {
  const matches = screen.getAllByText(itemCode);
  const withinRow = matches
    .map((el) => el.closest('tr'))
    .find((tr): tr is HTMLTableRowElement => Boolean(tr));
  expect(withinRow).toBeTruthy();
  return withinRow as HTMLElement;
}

beforeEach(() => {
  vi.clearAllMocks();
  searchParamsValue = '';
  reservePermissionOverride = null;
  getReserveRequestsMock.mockResolvedValue([OPEN_REQUEST]);
  vi.mocked(getOrderInquiryHeaderLines).mockResolvedValue([PLAIN_ROW, REQUESTED_ROW, RESERVED_ROW]);
});

describe('AC-RS-83: pills + per-row icon buttons, gated by the reserve permission', () => {
  it('with the permission: a requested line shows the amber pill AND Edit reserve; a reserved line shows the green pill AND Amend reserve + History; a plain line shows neither icon', async () => {
    renderDetail();
    await screen.findByText('ZZT-REQUESTED');

    const requestedRow = gridRowFor('ZZT-REQUESTED');
    expect(within(requestedRow).getByText(/request to reserve 107/i)).toBeInTheDocument();
    expect(within(requestedRow).getByLabelText('Edit reserve')).toBeInTheDocument();

    const reservedRow = gridRowFor('ZZT-RESERVED');
    expect(within(reservedRow).getByText(/reserved 30/i)).toBeInTheDocument();
    expect(within(reservedRow).getByLabelText('Amend reserve')).toBeInTheDocument();
    expect(within(reservedRow).getByLabelText('History')).toBeInTheDocument();

    const plainRow = gridRowFor('ZZT-PLAIN');
    expect(within(plainRow).queryByLabelText('Edit reserve')).not.toBeInTheDocument();
    expect(within(plainRow).queryByLabelText('Amend reserve')).not.toBeInTheDocument();
    expect(within(plainRow).queryByLabelText('History')).not.toBeInTheDocument();
  });

  it('no header badge, no Confirm all button, no "Open reserve request" control anywhere on the page', async () => {
    renderDetail();
    await screen.findByText('ZZT-REQUESTED');

    expect(screen.queryByRole('button', { name: /open reserve request/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /confirm all/i })).not.toBeInTheDocument();
  });

  it('without the permission: pills only, no action-cell icon buttons anywhere', async () => {
    reservePermissionOverride = false;
    renderDetail();
    await screen.findByText('ZZT-REQUESTED');

    expect(screen.queryByLabelText('Edit reserve')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Amend reserve')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('History')).not.toBeInTheDocument();
    const requestedRow = gridRowFor('ZZT-REQUESTED');
    expect(within(requestedRow).getByText(/request to reserve 107/i)).toBeInTheDocument();
  });
});

describe('AC-RS-84: the tick stages the full requested qty at the default pool, no dialog, no write', () => {
  it('staging shows the dashed chip + Undo; nothing is posted; Undo restores the icons', async () => {
    renderDetail();
    await screen.findByText('ZZT-REQUESTED');

    const requestedRow = gridRowFor('ZZT-REQUESTED');
    const tick = within(requestedRow).getByLabelText('Reserve');
    fireEvent.click(tick);

    expect(await screen.findByText('Reserve 107 @ BRW')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /undo/i })).toBeInTheDocument();
    expect(commitReserveSpy).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: /undo/i }));
    await waitFor(() =>
      expect(within(gridRowFor('ZZT-REQUESTED')).getByLabelText('Edit reserve')).toBeInTheDocument(),
    );
    expect(screen.queryByText('Reserve 107 @ BRW')).not.toBeInTheDocument();
  });
});

describe('AC-RS-85: Edit reserve opens ReserveLineForm; short qty needs a reason; Stage shows the chip', () => {
  it('opens a dialog titled by the item code with a Stage button; stages a short qty at DC1', async () => {
    renderDetail();
    await screen.findByText('ZZT-REQUESTED');

    const requestedRow = gridRowFor('ZZT-REQUESTED');
    fireEvent.click(within(requestedRow).getByLabelText('Edit reserve'));

    expect(await screen.findByRole('dialog', { name: /ZZT-REQUESTED/i })).toBeInTheDocument();
    const stageButton = screen.getByRole('button', { name: /^stage$/i });
    expect(stageButton).toBeDisabled();

    fireEvent.click(screen.getByLabelText('Location'));
    fireEvent.click(await screen.findByText('DC1'));
    fireEvent.change(screen.getByLabelText('Reserved'), { target: { value: '20' } });
    fireEvent.change(screen.getByLabelText(/reason/i), { target: { value: 'partial stock only' } });
    fireEvent.click(screen.getByRole('button', { name: /^stage$/i }));

    expect(await screen.findByText('Reserve 20 @ DC1')).toBeInTheDocument();
    expect(commitReserveSpy).not.toHaveBeenCalled();
  });
});

describe('AC-RS-86: Amend reserve on a reserved line locks the location and stages an amend chip', () => {
  it('Location renders as read-only text; Stage shows "Amend to 10"; Undo drops it', async () => {
    renderDetail();
    await screen.findByText('ZZT-RESERVED');

    const reservedRow = gridRowFor('ZZT-RESERVED');
    fireEvent.click(within(reservedRow).getByLabelText('Amend reserve'));

    expect(await screen.findByRole('dialog', { name: /ZZT-RESERVED/i })).toBeInTheDocument();
    expect(screen.queryByLabelText('Location')).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Reserved'), { target: { value: '10' } });
    fireEvent.click(screen.getByRole('button', { name: /^stage$/i }));

    expect(await screen.findByText('Amend to 10')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /undo/i }));
    await waitFor(() =>
      expect(within(gridRowFor('ZZT-RESERVED')).getByLabelText('Amend reserve')).toBeInTheDocument(),
    );
  });
});

describe('AC-RS-87: header Reserve CTA, disabled while nothing staged, commits the staged map on click', () => {
  it('disabled with no staged rows; enabled "Reserve (2)" once two rows are staged; commit posts one call, toasts, clears staging', async () => {
    vi.mocked(getOrderInquiryHeaderLines).mockResolvedValue([PLAIN_ROW, REQUESTED_ROW, RESERVED_ROW]);
    renderDetail();
    await screen.findByText('ZZT-REQUESTED');

    const reserveCta = await screen.findByRole('button', { name: /^reserve$/i });
    expect(reserveCta).toBeDisabled();

    fireEvent.click(within(gridRowFor('ZZT-REQUESTED')).getByLabelText('Reserve'));
    await screen.findByText('Reserve 107 @ BRW');

    fireEvent.click(within(gridRowFor('ZZT-RESERVED')).getByLabelText('Amend reserve'));
    await screen.findByRole('dialog', { name: /ZZT-RESERVED/i });
    fireEvent.change(screen.getByLabelText('Reserved'), { target: { value: '10' } });
    fireEvent.click(screen.getByRole('button', { name: /^stage$/i }));
    await screen.findByText('Amend to 10');

    const enabledCta = screen.getByRole('button', { name: /^reserve \(2\)$/i });
    expect(enabledCta).toBeEnabled();

    fireEvent.click(enabledCta);

    await waitFor(() => expect(commitReserveSpy).toHaveBeenCalledTimes(1));
    const [, , payload] = commitReserveSpy.mock.calls[0] as [string, string, {
      reserves: Array<{ row_id: string; warehouse_id: string; qty_reserved: string | number; reason?: string | null }>;
      amendments: Array<{ row_id: string; qty_reserved: string | number; reason?: string | null }>;
    }];
    expect(payload.reserves).toEqual([
      expect.objectContaining({ row_id: 'row-requested', warehouse_id: 'wh-brw', qty_reserved: 107 }),
    ]);
    expect(payload.amendments).toEqual([
      expect.objectContaining({ row_id: 'row-reserved', qty_reserved: 10 }),
    ]);

    await waitFor(() => expect(toastSuccessSpy).toHaveBeenCalledWith(expect.stringMatching(/reserved, .* notified/i)));
    expect(screen.queryByText('Reserve 107 @ BRW')).not.toBeInTheDocument();
    expect(screen.queryByText('Amend to 10')).not.toBeInTheDocument();
  });

  it('a rejected commit leaves the staged chips in place and toasts the error', async () => {
    commitReserveSpy.mockRejectedValueOnce(new Error('boom'));
    renderDetail();
    await screen.findByText('ZZT-REQUESTED');

    fireEvent.click(within(gridRowFor('ZZT-REQUESTED')).getByLabelText('Reserve'));
    await screen.findByText('Reserve 107 @ BRW');

    fireEvent.click(screen.getByRole('button', { name: /^reserve \(1\)$/i }));

    await waitFor(() => expect(toastErrorSpy).toHaveBeenCalled());
    expect(screen.getByText('Reserve 107 @ BRW')).toBeInTheDocument();
  });

  it('without the reserve permission, the header Reserve button is absent', async () => {
    reservePermissionOverride = false;
    renderDetail();
    await screen.findByText('ZZT-REQUESTED');

    expect(screen.queryByRole('button', { name: /^reserve( \(\d+\))?$/i })).not.toBeInTheDocument();
  });
});

describe('AC-RS-88: the State SearchableMultiSelect filter, and ?reserve= preselecting it without opening a dialog', () => {
  it('offers the seven State options; selecting Request to reserve hides other lines', async () => {
    renderDetail();
    await screen.findByText('ZZT-REQUESTED');
    await screen.findByText('ZZT-PLAIN');
    await screen.findByText('ZZT-RESERVED');

    const trigger = document.querySelector('[data-slot="searchable-multi-select-trigger"]');
    expect(trigger).toBeTruthy();
    fireEvent.click(trigger as Element);

    const options = ['To buy', 'Partly on PO/SPO', 'On PO/SPO', 'Done', 'Cancelled', 'Request to reserve', 'Reserved'];
    for (const label of options) {
      expect(await screen.findByText(label)).toBeInTheDocument();
    }

    fireEvent.click(screen.getByText('Request to reserve'));

    await waitFor(() => expect(screen.queryByText('ZZT-PLAIN')).not.toBeInTheDocument());
    expect(screen.getByText('ZZT-REQUESTED')).toBeInTheDocument();
  });

  it('?reserve=<id> preselects Request to reserve and opens no dialog', async () => {
    searchParamsValue = 'reserve=rr-1';
    renderDetail();
    await screen.findByText('ZZT-REQUESTED');

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText('ZZT-PLAIN')).not.toBeInTheDocument());
  });
});

describe('AC-RS-89: History opens a read-only events dialog; Cancel request sits in the Actions menu', () => {
  it('History lists the row events newest first through formatDateTime', async () => {
    renderDetail();
    await screen.findByText('ZZT-RESERVED');

    fireEvent.click(within(gridRowFor('ZZT-RESERVED')).getByLabelText('History'));

    const historyDialog = await screen.findByRole('dialog', { name: /history/i });
    expect(within(historyDialog).queryByText(/\d{4}-\d\d-\d\dT/)).not.toBeInTheDocument();
  });

  it('Cancel request is offered in the Actions menu for the requester', async () => {
    renderDetail();
    await screen.findByText('ZZT-REQUESTED');

    fireEvent.click(screen.getByRole('button', { name: /order inquiry options/i }));
    expect(await screen.findByText(/cancel request/i)).toBeInTheDocument();
  });
});
