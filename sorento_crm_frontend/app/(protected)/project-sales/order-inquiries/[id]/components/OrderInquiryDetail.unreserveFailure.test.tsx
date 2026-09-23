/**
 * `PLAN-oi-request-cs-reserve.md` section 6c F5 gap fix (round 2 browser evidence,
 * `postfix-linescope-above-net-silent.png`): Unreserve is a server-deferred pending
 * action (`useDeferredAction`, `order_inquiry_reserve_row.unreserve`) - a commit that
 * FAILS at the server (the backend's own named-limit 422, turned `ineligible` by
 * `FormActionService.commit_one`, both read `failed` on the wire) has to reach the
 * reader as a toast: a countdown that simply disappears reads exactly like success.
 *
 * `useDeferredAction`'s own generic mechanism already does this
 * (`pendingEntityStore.announceOutcome`, pinned generically for `product.delete` in
 * `hooks/useDeferredAction.test.tsx`) - this file proves the SAME thing for the ACTUAL
 * wiring `OrderInquiryDetail.tsx` builds (`reserveRowUnreserveAction`), through the
 * rendered harness `OrderInquiryDetail.reserveIcon.test.tsx` already uses, rather than
 * assuming the generic hook test covers this control's own props.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
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

const toastSuccess = vi.fn();
const toastError = vi.fn();
vi.mock('@/lib/toast', () => ({
  toast: {
    success: (...args: unknown[]) => toastSuccess(...args),
    error: (...args: unknown[]) => toastError(...args),
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
  lines_total: 1,
  lines_to_confirm: 0,
  qty_total: '50',
  status: 'outstanding',
  order_type: null,
  raise_history: [],
};

function row(over: Partial<OrderInquiryWorklistRow>): OrderInquiryWorklistRow {
  return {
    id: 'row-reserved',
    order_inquiry_id: 'oi-1',
    item_code: 'ZZT-RESERVED',
    qty: '50',
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
    reserved_qty: '50',
    reserve_state: 'reserved',
    ...over,
  } as unknown as OrderInquiryWorklistRow;
}

const RESERVED_ROW = row({});

// The request that still holds the reserve link - the same shape
// `OrderInquiryDetail.reserveIcon.test.tsx`'s own "Re-review finding 1" fixture uses,
// so `reserveRowEffectiveRequestId` resolves to a real request id (the deferred
// action's own required `request_id` payload key).
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

vi.mock('../../../_shared/services/orderInquiryService', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('../../../_shared/services/orderInquiryService')>();
  return {
    ...actual,
    getOrderInquiryHeader: vi.fn(async () => HEADER),
    getOrderInquiryHeaderLines: vi.fn(async () => [RESERVED_ROW]),
    getOrderInquiryHeaderRelatedDocuments: vi.fn(async () => ({ purchase_orders: [], spos: [] })),
    listOrderInquiryHeaders: vi.fn(async () => ({ data: [], total: 0, page: 1, limit: 25 })),
    acknowledgeOrderInquiryRowsByFilter: vi.fn(async () => ({ acknowledged: 0, results: [] })),
    acknowledgeOrderInquiryRows: vi.fn(async () => ({ acknowledged: 0, results: [] })),
    autoPlaceOrderInquiryRows: vi.fn(async () => ({ linked: 0, results: [] })),
  };
});

const getReserveRequestsMock = vi.fn(async () => [REQUEST_WITH_LINK]);
vi.mock('../../../_shared/services/orderInquiryReserveService', () => ({
  createOrderInquiryReserveRequest: vi.fn(async () => ({
    id: 'rr-2', ordinal: 2, first_to_name: 'Eling',
  })),
  getOrderInquiryReserveRequests: (...args: unknown[]) =>
    getReserveRequestsMock(...(args as [string])),
  reserveOrderInquiryRow: vi.fn(async () => ({ id: 'reqrow-with-link' })),
  getOrderInquiryRowHistory: vi.fn(async () => []),
}));

const ERROR_TEXT = 'ZZT-RESERVED: unreserve quantity must be between 0 and 50 (the net reserved).';

const PARKED_ACTION = {
  id: 'pa-unreserve-1',
  action_key: 'order_inquiry_reserve_row.unreserve',
  entity_type: 'order_inquiry_reserve_row',
  entity_id: 'row-reserved',
  commit_at: new Date(Date.now() + 10_000).toISOString(),
  window_seconds: 10,
};

// `useDeferredAction` polls `current` every 500ms REAL time while something is parked
// (`refetchInterval`) - `serverState` is what that poll answers, mutable so the test can
// hold "still pending" for as long as `start` really would (the grace window), and only
// flip to the failed outcome on its own cue, the same way `commit_at` actually lapsing
// would. A fixed `{ pending: null }` answer here would race the natural 500ms poll and
// clear `pending` with NO outcome before the test ever asks for the failure - a test
// bug that reads exactly like the product bug this file is proving does NOT exist.
let serverState: { pending: unknown; last_outcome: unknown } = { pending: null, last_outcome: null };

const createPendingActionSpy = vi.fn(async ({ entityId }: { entityId: string }) => {
  serverState = { pending: { ...PARKED_ACTION, entity_id: entityId }, last_outcome: null };
  return PARKED_ACTION;
});
const getCurrentPendingActionSpy = vi.fn(async () => serverState);
vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: (...args: unknown[]) =>
    createPendingActionSpy(...(args as [{ entityId: string }])),
  cancelPendingAction: vi.fn(async () => undefined),
  getCurrentPendingAction: (...args: unknown[]) => getCurrentPendingActionSpy(...args),
}));

import { pendingEntityStore } from '@/lib/pending-entity-store';
import { OrderInquiryDetail } from './OrderInquiryDetail';

function renderDetail() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const utils = render(
    <QueryClientProvider client={client}>
      <OrderInquiryDetail id="oi-1" />
    </QueryClientProvider>,
  );
  return { ...utils, client };
}

function gridRowFor(itemCode: string): HTMLElement {
  const matches = screen.getAllByText(itemCode);
  const withinRow = matches.map((el) => el.closest('tr')).find((tr): tr is HTMLTableRowElement => Boolean(tr));
  expect(withinRow).toBeTruthy();
  return withinRow as HTMLElement;
}

beforeEach(() => {
  vi.clearAllMocks();
  // Module-level state is per TAB (`lib/pending-entity-store.ts`'s own note) - the
  // outcome dedupe would otherwise carry `pa-unreserve-1` from one test into the next.
  pendingEntityStore.reset();
  getReserveRequestsMock.mockResolvedValue([REQUEST_WITH_LINK]);
  serverState = { pending: null, last_outcome: null };
});

describe('gap fix: a failed Unreserve commit toasts the server text, not silence', () => {
  it('the window settling `failed` reaches the reader as one error toast carrying error_text', async () => {
    const { client } = renderDetail();
    await screen.findByText('ZZT-RESERVED');

    fireEvent.click(gridRowFor('ZZT-RESERVED').querySelector('[aria-label="Reserve"]') as Element);
    await screen.findByRole('tab', { name: /reserve/i });
    fireEvent.click(await screen.findByRole('button', { name: /^unreserve$/i }));
    fireEvent.change(await screen.findByLabelText(/qty/i), { target: { value: '20' } });
    fireEvent.click(screen.getByRole('button', { name: /^unreserve$/i }));

    await waitFor(() => expect(createPendingActionSpy).toHaveBeenCalledTimes(1));

    // The window lapses - the server commits it `ineligible` (the 422's own named
    // limit, turned `failed` on the wire by `pending_actions.py`'s `_OUTCOME_STATUS`).
    serverState = {
      pending: null,
      last_outcome: {
        id: 'pa-unreserve-1',
        action_key: 'order_inquiry_reserve_row.unreserve',
        status: 'failed',
        error_text: ERROR_TEXT,
        ended_at: new Date().toISOString().replace(/\.\d+Z$/, ''),
      },
    };
    await act(async () => {
      await client.refetchQueries({ queryKey: ['pending-action-current'] });
    });

    await waitFor(() =>
      expect(toastError).toHaveBeenCalledWith(ERROR_TEXT, expect.anything()),
    );
    expect(toastError).toHaveBeenCalledTimes(1);
    expect(toastSuccess).not.toHaveBeenCalledWith('Unreserved', expect.anything());
  });
});
