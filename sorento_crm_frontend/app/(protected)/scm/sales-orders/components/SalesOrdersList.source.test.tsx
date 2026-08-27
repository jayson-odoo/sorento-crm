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



// The Plan action asks whether this user may open the fulfilment board. `useHasPermission`
// reaches for the NextAuth session, which is not mounted under jsdom, so it is stubbed the
// same way the proforma-invoice view's own suite stubs it.
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => true,
  usePermissions: () => ({ permissions: [], permissionSet: new Set(), isLoading: false }),
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
  useSalesOrderAgents: () => ({ data: [], isLoading: false }),
  useCreateSalesOrder: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdateSalesOrder: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useDeleteSalesOrder: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useResetSalesOrderPlanning: () => ({ mutateAsync: vi.fn(), isPending: false }),
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
    // The distinction IS the feature: it decides whose figures win. Read "Upload" (A4, the
    // captain 27 Aug): the column is called Source and every row of this list is already a
    // sales order, so "Sales order upload" spent two of its three words repeating the screen
    // it is on.
    stub([order({ source: 'upload' })]);
    renderList();

    expect(await screen.findByText('Upload')).toBeInTheDocument();
  });

  it('defaults to Manual when the backend says nothing', async () => {
    stub([order({ source: undefined })]);
    renderList();

    expect(await screen.findByText('Manual')).toBeInTheDocument();
  });
});

describe('SalesOrdersList - location is a line-level fact, not a header one', () => {
  it('does not carry a Location column at all', async () => {
    // One order routinely lands in two warehouses, so a header cell showing "BRW-IB, KL-01"
    // says less than the lines grid on the detail page, which says WHICH line goes where.
    stub([order()]);
    renderList();

    await waitFor(() => expect(screen.getByText('SO900001')).toBeInTheDocument());
    expect(screen.queryByText('BRW-IB')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Location' })).toBeNull();
  });
});

describe('SalesOrdersList - the row actions', () => {
  it('offers delete only - the row itself is the way into the order', async () => {
    // Create DO and the pencil both went: the whole row already opens the detail page, where
    // editing happens in place, and raising a delivery is a delivery decision rather than a
    // list one.
    stub([order()]);
    renderList();

    await waitFor(() => expect(screen.getByText('SO900001')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: 'Delete' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Create DO/i })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Edit' })).toBeNull();
  });

  it('confirms before deleting, rather than deleting on the click', async () => {
    stub([order()]);
    renderList();

    await waitFor(() => expect(screen.getByText('SO900001')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));

    expect(await screen.findByText(/This action cannot be undone/i)).toBeInTheDocument();
  });
});

describe('SalesOrdersList - linkage', () => {
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

describe('SalesOrdersList - the pills follow the sales-agents master', () => {
  /**
   * The captain's reference for a pill is the sales-agents page: a light filled chip. The
   * status used to be the exception - a ghost chip with a dot, on the theory that a STATE is
   * a different kind of thing from an ENUM - and that exception is gone: "pure green
   * bulleted point word is a no-no". One pill family on the screen, colour carried by the
   * chip.
   *
   * The WORDS follow AutoCount, the system this book is exported from and the one the client
   * reads all day: `open` is Outstanding, `closed` is Completed. The stored values are
   * untouched - only the label is.
   */
  const badgeFor = (label: string) =>
    screen.getByText(label).closest('[data-slot="badge"]') as HTMLElement | null;

  it('words an open order "Outstanding" and a closed one "Completed"', async () => {
    stub([order({ status: 'open' }), order({ so_number: 'SO2', status: 'closed' })]);
    renderList();

    await screen.findByText('Outstanding');
    expect(screen.getByText('Completed')).toBeInTheDocument();
    expect(screen.queryByText('Open')).not.toBeInTheDocument();
    expect(screen.queryByText('Closed')).not.toBeInTheDocument();
  });

  it('paints a status as a light chip - no dot, and no ghost', async () => {
    // It WAS a ghost chip with a dot. The captain's verdict on a bare green dot beside a
    // word ("pure green bulleted point word is a no-no") is what retired it: the status now
    // wears the same light family as every other pill in the table, and the colour is
    // carried by the chip rather than by a dot floating in a transparent box.
    stub([order({ status: 'open' })]);
    renderList();

    await screen.findByText('Outstanding');
    const badge = badgeFor('Outstanding');
    expect(badge).not.toBeNull();
    expect(badge?.className).not.toContain('bg-transparent');
    expect(badge?.className).toContain('--color-success-soft');
    expect(badge?.querySelector('[data-slot="badge-dot"]')).toBeNull();
  });

  it('paints the priority from the priority table: normal is neutral, urgent shouts', async () => {
    // The system status table calls 'normal' a success and 'low' destructive, which is
    // stock-health semantics. Priority keeps its own variants, on a light filled chip.
    stub([order({ priority: 'normal' }), order({ so_number: 'SO2', priority: 'urgent' })]);
    renderList();

    await screen.findByText('Normal');
    const normal = badgeFor('Normal');
    expect(normal).not.toBeNull();
    expect(normal?.className).toContain('bg-secondary');

    const urgent = badgeFor('Urgent');
    expect(urgent).not.toBeNull();
    // The light palette, the same one the sales-agents master's enum pills wear.
    expect(urgent?.className).toContain('soft');
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

    fireEvent.change(screen.getByPlaceholderText('Search SO, customer, product or agent...'), {
      target: { value: 'SO999999' },
    });

    expect(
      await screen.findByText('No sales order matches this search and filter.'),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Upload the Order Inquiry sheet/)).toBeNull();
  });
});

describe('SalesOrdersList - the Type column reads the planning class', () => {
  // `order_type_label` (the ERP document type) is blank on nearly every row in this book -
  // the classification agents' `demand_class` is what actually answers "what type is this".

  it('shows a Project chip for a project-classified order', async () => {
    stub([order({ demand_class: 'project', order_type_label: '' })]);
    renderList();

    expect(await screen.findByText('Project')).toBeInTheDocument();
  });

  it('shows a Retail chip for a retail-classified order', async () => {
    stub([order({ demand_class: 'retail', order_type_label: '' })]);
    renderList();

    expect(await screen.findByText('Retail')).toBeInTheDocument();
  });

  it('shows a muted "Unclassified" chip rather than an empty cell', async () => {
    stub([order({ demand_class: null, order_type_label: '' })]);
    renderList();

    expect(await screen.findByText('Unclassified')).toBeInTheDocument();
  });

  it('shows the stated document type as a subline when it differs from the class', async () => {
    stub([order({ demand_class: 'project', order_type_label: 'Contract Sale' })]);
    renderList();

    expect(await screen.findByText('Project')).toBeInTheDocument();
    expect(await screen.findByText('Contract Sale')).toBeInTheDocument();
  });

  it('does not repeat the document type when it already says the same thing as the class', async () => {
    stub([order({ demand_class: 'project', order_type_label: 'Project' })]);
    renderList();

    await waitFor(() => expect(screen.getByText('SO900001')).toBeInTheDocument());
    // Exactly one "Project" - the chip - not a second copy as the subline.
    expect(screen.getAllByText('Project')).toHaveLength(1);
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
