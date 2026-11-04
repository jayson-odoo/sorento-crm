/**
 * OI-RESERVE-ROUND fix round 2: the OI page's prev / next pager must survive every action
 * taken on the page. Each action's success invalidates the whole `[ORDER_INQUIRY_HEADERS_KEY]`
 * list prefix, the pager's own query refetches, and the OI no longer matches the list it was
 * opened from (it moved state or page), so the refetched page lacks it.
 *
 * Harness: the real `OrderInquiryDetail` (with its real pager) and a sibling driver that
 * calls the REAL mutation hooks each button calls, with the services under them mocked. The
 * hook's own invalidation set therefore runs against the same QueryClient the pager reads.
 * The first list answer holds this OI; every later one does not.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { OrderInquiryHeaderDetail } from '../../../_shared/types/orderInquiry.types';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => '/project-sales/order-inquiries/oi-1',
  useSearchParams: () => new URLSearchParams('page=1&limit=25&state=outstanding'),
}));
vi.mock('@/hooks/usePermissions', () => ({ useHasPermission: () => true }));
vi.mock('next-auth/react', () => ({
  useSession: () => ({ data: { user: { id: 'u-1' } }, status: 'authenticated' }),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), dismiss: vi.fn() },
}));
vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: vi.fn(),
  cancelPendingAction: vi.fn(async () => undefined),
  getCurrentPendingAction: vi.fn(async () => ({ pending: null, last_outcome: null })),
}));
vi.mock('../../../_shared/services/fulfilmentPlanningService', () => ({
  getStockDetail: vi.fn(async () => ({ locations: [] })),
}));

const HEADER = {
  id: 'oi-1',
  inquiry_no: 'OI-2609-0001',
  raised_at: '2026-09-05T08:00:00',
  raised_by_name: 'Requester',
  sales_order_id: 'so-1',
  project_sales_order_id: 'pso-1',
  so_number: 'SO123456',
  customer_name: 'Customer',
  lines_total: 0,
  lines_to_confirm: 0,
  qty_total: '0',
  status: 'outstanding',
  raise_history: [],
} as unknown as OrderInquiryHeaderDetail;

const listCalls = vi.hoisted(() => ({ n: 0 }));
const ack = { acknowledged: 1, skipped: 0, results: [], linked: 0, not_linked: 0, updated: 1 };

vi.mock('../../../_shared/services/orderInquiryService', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('../../../_shared/services/orderInquiryService')>();
  return {
    ...actual,
    getOrderInquiryHeader: vi.fn(async () => HEADER),
    getOrderInquiryHeaderLines: vi.fn(async () => []),
    getOrderInquiryHeaderRelatedDocuments: vi.fn(async () => ({ purchase_orders: [], spos: [] })),
    listOrderInquiryHeaders: vi.fn(async () => {
      listCalls.n += 1;
      const data =
        listCalls.n === 1
          ? [{ id: 'oi-0' }, { id: 'oi-1' }, { id: 'oi-2' }]
          : [{ id: 'oi-0' }, { id: 'oi-2' }];
      return { data, pagination: { total: data.length } };
    }),
    acknowledgeOrderInquiryRows: vi.fn(async () => ack),
    unacknowledgeOrderInquiryRows: vi.fn(async () => ack),
    rejectOrderInquiryRow: vi.fn(async () => ack),
    rejectOrderInquiryRows: vi.fn(async () => ack),
    linkNowOrderInquiryRows: vi.fn(async () => ack),
    autoPlaceOrderInquiryRows: vi.fn(async () => ack),
    placeOrderInquiryRowOnPo: vi.fn(async () => ({})),
    placeOrderInquiryRowOnPoAllocations: vi.fn(async () => ({})),
    unplaceOrderInquiryRow: vi.fn(async () => ({})),
  };
});
vi.mock('../../../_shared/services/orderInquiryReserveService', async (importOriginal) => {
  const actual = await importOriginal<
    typeof import('../../../_shared/services/orderInquiryReserveService')
  >();
  return {
    ...actual,
    getOrderInquiryReserveRequests: vi.fn(async () => []),
    commitOrderInquiryReserve: vi.fn(async () => [{ id: 'rr-1' }]),
    createOrderInquiryReserveRequest: vi.fn(async () => ({ id: 'rr-2', ordinal: 2, first_to_name: 'CS' })),
    sendParkedReserveNotices: vi.fn(async () => ({ emails_sent: 1, items_sent: 1 })),
    sendParkedReserveRequests: vi.fn(async () => ({ emails_sent: 1, items_sent: 1 })),
  };
});

import { OrderInquiryDetail } from './OrderInquiryDetail';
import {
  ORDER_INQUIRY_HEADERS_KEY,
  useAutoPlaceOrderInquiryRows,
  useCommitOrderInquiryReserve,
  useCreateOrderInquiryReserveRequest,
  useOrderInquiryHandshake,
  useOrderInquiryPlacementMutations,
  useSendParked,
} from '../../../_shared/hooks/useOrderInquiry';

type Fire = () => Promise<unknown>;
const fire: Record<string, Fire> = {};

function Driver() {
  const commit = useCommitOrderInquiryReserve('oi-1');
  const create = useCreateOrderInquiryReserveRequest('oi-1');
  const handshake = useOrderInquiryHandshake();
  const autoPlace = useAutoPlaceOrderInquiryRows();
  const placement = useOrderInquiryPlacementMutations();
  const sendNotices = useSendParked('notices');
  const sendRequests = useSendParked('requests');
  const ignore = (p: Promise<unknown>) => p.catch(() => undefined);
  fire['Reserve (immediate commit)'] = () =>
    ignore(commit.mutateAsync({ payload: { reserves: [{ row_id: 'r', warehouse_id: 'w', qty_reserved: '5' }], amendments: [] } as never }));
  fire['Reserve with Park notice first'] = () =>
    ignore(commit.mutateAsync({ payload: { reserves: [{ row_id: 'r', warehouse_id: 'w', qty_reserved: '5' }], amendments: [], park_notice: true } as never }));
  fire['Reject (reserve 0)'] = () =>
    ignore(commit.mutateAsync({ payload: { reserves: [{ row_id: 'r', warehouse_id: 'w', qty_reserved: '0', reason: 'none' }], amendments: [] } as never }));
  fire['Amend reserve'] = () =>
    ignore(commit.mutateAsync({ payload: { reserves: [], amendments: [{ row_id: 'r', qty_reserved: '3' }] } as never }));
  fire['Request CS to reserve'] = () =>
    ignore(create.mutateAsync({ rows: [{ row_id: 'r', qty_requested: '5', warehouse_id: 'w' }] } as never));
  fire['Request CS to reserve (park)'] = () =>
    ignore(create.mutateAsync({ rows: [{ row_id: 'r', qty_requested: '5', warehouse_id: 'w' }], park: true } as never));
  fire['Confirm (acknowledge)'] = () => ignore(handshake.acknowledge.mutateAsync({ rowIds: ['r'] } as never));
  fire['Unconfirm'] = () => ignore(handshake.unacknowledge.mutateAsync(['r'] as never));
  fire['Reject row (handshake)'] = () => ignore(handshake.reject.mutateAsync({ rowId: 'r', reason: 'x' } as never));
  fire['Reject rows (handshake)'] = () => ignore(handshake.rejectRows.mutateAsync({ rowIds: ['r'], reason: 'x' } as never));
  fire['Link now'] = () => ignore(handshake.linkNow.mutateAsync({} as never));
  fire['Auto link'] = () => ignore(autoPlace.mutateAsync({ row_ids: ['r'] } as never));
  fire['Link selected / Choose document'] = () => ignore(placement.place.mutateAsync({ rowId: 'r', poLineId: 'p' } as never));
  fire['Unlink'] = () => ignore(placement.unplace.mutateAsync({ rowId: 'r' } as never));
  fire['Send parked notices'] = () => ignore(sendNotices.mutateAsync());
  fire['Send parked requests'] = () => ignore(sendRequests.mutateAsync());
  return null;
}

let client: QueryClient;

beforeEach(() => {
  listCalls.n = 0;
  client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
});

const ACTIONS = [
  'Reserve (immediate commit)',
  'Reserve with Park notice first',
  'Reject (reserve 0)',
  'Amend reserve',
  'Request CS to reserve',
  'Request CS to reserve (park)',
  'Confirm (acknowledge)',
  'Unconfirm',
  'Reject row (handshake)',
  'Reject rows (handshake)',
  'Link now',
  'Auto link',
  'Link selected / Choose document',
  'Unlink',
  'Send parked notices',
  'Send parked requests',
];

describe('the OI page pager survives every action that refreshes the header list', () => {
  it.each(ACTIONS)('%s', async (action) => {
    render(
      <QueryClientProvider client={client}>
        <OrderInquiryDetail id="oi-1" />
        <Driver />
      </QueryClientProvider>,
    );
    // Wait for the first list answer to land (the counter), not just the loading pager.
    await screen.findByText('2 / 3');
    expect(screen.getByRole('button', { name: /previous order inquiry/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /next order inquiry/i })).toBeInTheDocument();

    await act(async () => {
      await fire[action]();
    });
    // The success invalidation has refetched the list, and the OI is gone from the page.
    await waitFor(() => expect(listCalls.n).toBeGreaterThanOrEqual(2));

    expect(screen.getByRole('button', { name: /previous order inquiry/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /next order inquiry/i })).toBeInTheDocument();
  });

  it('the page action that only invalidates the list prefix (unlink countdown, cancel request) keeps it too', async () => {
    render(
      <QueryClientProvider client={client}>
        <OrderInquiryDetail id="oi-1" />
      </QueryClientProvider>,
    );
    await screen.findByText('2 / 3');
    await act(async () => {
      await client.invalidateQueries({ queryKey: [ORDER_INQUIRY_HEADERS_KEY] });
    });
    await waitFor(() => expect(listCalls.n).toBeGreaterThanOrEqual(2));
    expect(screen.getByRole('button', { name: /previous order inquiry/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /next order inquiry/i })).toBeInTheDocument();
  });
});
