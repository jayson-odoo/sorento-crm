/**
 * N5 - the sales-order list says where each order came from, where it lands, and what it
 * waits on.
 *
 * > "it should be a list of SO basically, cause order inquiry is essentially SO ... then the
 * > linkage also needs to be visualized, location etc"
 *
 * Scoped to the three columns and the one filter this slice added. The list's existing
 * behaviour (paging, delete, create-DO) is not re-tested here; what is asserted is that an
 * order the Order Inquiry sheet created is DISTINGUISHABLE from one CS uploaded, because that
 * is what decides who may edit its figures.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
    dispatchEvent: () => false,
  });
}
if (!window.ResizeObserver) {
  (window as unknown as { ResizeObserver: unknown }).ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

// The row-click handler asks for the router, which is not mounted under jsdom.
// PARTIAL. The grid and its toolbar reach for other exports of this module, and replacing it
// wholesale left them undefined - which showed up as a grid stuck on its loading skeleton
// rather than as an error.
vi.mock('next/navigation', async (importOriginal) => ({
  ...(await importOriginal<typeof import('next/navigation')>()),
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => '/scm/sales-orders',
  useSearchParams: () => new URLSearchParams(),
}));



// The grid asks for the user's saved column order via this hook, which reads the route to
// build its listing key. With `next/navigation` mocked the hook goes down its fetching path
// and the grid sits on its loading skeleton, so it is stubbed the same way the detail suite
// stubs it.
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

const useSalesOrders = vi.fn();
vi.mock('../../hooks/useSalesOrders', () => ({
  useSalesOrders: (...a: unknown[]) => useSalesOrders(...a),
  useCreateSalesOrder: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdateSalesOrder: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useDeleteSalesOrder: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useCreateDoFromSalesOrder: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

import SalesOrdersList from './SalesOrdersList';
import type { SalesOrder } from '../../types/scm.types';

function order(over: Partial<SalesOrder> = {}): SalesOrder {
  return {
    id: 'so-1',
    so_number: 'SO900001',
    order_type: 'project',
    order_type_label: 'Project',
    customer_code: '',
    customer_name: '',
    market_segment: null,
    priority: 'normal',
    status: 'open',
    order_date: '2026-07-01',
    requested_delivery_date: '2026-09-01',
    total_qty: 12,
    committed_qty: 12,
    lines: [],
    source: 'inquiry',
    internal_note: 'Order Inquiry project: HOMEPRO',
    stock_locations: ['BRW-IB'],
    linked_purchase_orders: [
      { po_number: 'PO-WAITING', item_code: 'CWB242', resolved: false },
      { po_number: 'PO-MATCHED', item_code: null, resolved: true },
    ],
    awaiting_purchase_orders: 1,
    created_at: '2026-07-01T00:00:00',
    ...over,
  } as SalesOrder;
}

/** The list's own hooks are mocked, but its children still reach for a client. */
function renderList() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <SalesOrdersList />
    </QueryClientProvider>,
  );
}

function stub(rows: SalesOrder[]) {
  useSalesOrders.mockReturnValue({
    data: { data: rows, pagination: { total: rows.length, page: 1, limit: 50 }, empty: !rows.length },
    isLoading: false,
    isFetching: false,
    refetch: vi.fn(),
  });
}

beforeEach(() => {
  useSalesOrders.mockReset();
});

describe('SalesOrdersList - where an order came from', () => {
  it('labels an order the Order Inquiry sheet created', async () => {
    stub([order()]);
    renderList();

    expect(await screen.findByText('Order inquiry')).toBeInTheDocument();
  });

  it('labels an order CS uploaded differently', async () => {
    // The distinction IS the feature: it decides whose figures win.
    stub([order({ source: 'upload' })]);
    renderList();

    expect(await screen.findByText('Outstanding upload')).toBeInTheDocument();
  });

  it('defaults to Manual when the backend says nothing', async () => {
    stub([order({ source: undefined })]);
    renderList();

    expect(await screen.findByText('Manual')).toBeInTheDocument();
  });
});

describe('SalesOrdersList - location and linkage', () => {
  it('shows where the order lands', async () => {
    stub([order()]);
    renderList();

    expect(await screen.findByText('BRW-IB')).toBeInTheDocument();
  });

  it('shows only the purchase orders still being waited on', async () => {
    // "Which of my orders is stuck behind a PO we have not received" is the question, and
    // listing the matched ones alongside would bury the answer.
    stub([order()]);
    renderList();

    expect(await screen.findByText('PO-WAITING')).toBeInTheDocument();
    expect(screen.queryByText('PO-MATCHED')).toBeNull();
  });

  it('says nothing is waiting rather than rendering an empty cell', async () => {
    stub([
      order({
        linked_purchase_orders: [{ po_number: 'PO-MATCHED', item_code: null, resolved: true }],
        awaiting_purchase_orders: 0,
      }),
    ]);
    renderList();

    await waitFor(() => expect(screen.getByText('SO900001')).toBeInTheDocument());
    expect(screen.queryByText('PO-MATCHED')).toBeNull();
  });
});

describe('SalesOrdersList - a long wait list stays readable', () => {
  it('names the first few purchase orders and counts the rest', async () => {
    // A real order in the live data waits on 23. Printing all of them renders as a wall of
    // text that says less than the first two plus a count.
    stub([
      order({
        linked_purchase_orders: Array.from({ length: 23 }, (_, i) => ({
          po_number: `PO-${String(i).padStart(3, '0')}`,
          item_code: null,
          resolved: false,
        })),
        awaiting_purchase_orders: 23,
      }),
    ]);
    renderList();

    expect(await screen.findByText(/PO-000, PO-001/)).toBeInTheDocument();
    expect(screen.getByText('+21 more')).toBeInTheDocument();
    expect(screen.queryByText(/PO-022/)).toBeNull();
  });
});

describe('SalesOrdersList - the empty book', () => {
  it('names the step that fills it rather than saying no data', async () => {
    // An order book is empty because nobody has uploaded the sheet yet, and "No data
    // available" leaves the user to guess that.
    stub([]);
    renderList();

    expect(await screen.findByText(/Upload the Order Inquiry sheet/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Reorder planning' })).toHaveAttribute(
      'href',
      '/scm/reorder',
    );
  });

  it('blames the filter when one is on, not the missing upload', async () => {
    // Telling a user to go upload when their own filter hid the rows sends them to the
    // wrong screen.
    stub([]);
    renderList();

    fireEvent.change(screen.getByPlaceholderText('Search SO or customer...'), {
      target: { value: 'SO999999' },
    });

    expect(
      await screen.findByText('No sales order matches this search and filter.'),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Upload the Order Inquiry sheet/)).toBeNull();
  });
});

describe('SalesOrdersList - the source filter', () => {
  it('asks the backend for every source by default', async () => {
    stub([order()]);
    renderList();

    await waitFor(() => expect(useSalesOrders).toHaveBeenCalled());
    const params = useSalesOrders.mock.calls.at(-1)?.[0] as { source: string | null };
    expect(params.source).toBeNull();
  });
});
