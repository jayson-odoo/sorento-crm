/**
 * The sales-order list is where planning starts, and where it reports back.
 *
 * Two halves of one idea: the business sees SALES ORDERS and ORDER INQUIRIES, and nothing
 * between them. There is no plan entity and no "Planning" column.
 *
 *  1. REPORTING BACK - each order names the inquiries raised against it, links to them, and
 *     says on hover who raised each one and how much of it purchasing has placed.
 *  2. STARTING - tick the orders, open Actions, press "Plan selected (N)", and the
 *     fulfilment board opens on them. The board IS the URL (`?orders=SO1,SO2`), so the
 *     action navigates and stores nothing.
 *
 * The action lives in the toolbar's Actions dropdown, NOT in the bulk strip. In the strip it
 * only existed once rows were ticked, so nobody who had not already found it could learn it
 * was there, and over the board's bound it was a greyed-out button whose reason was a hover
 * away - which is exactly the dead click that was reported.
 *
 * The bound (50) is the board's own `MAX_BOARD_SELECTION`. Over it the item is DISABLED with
 * the count in its reason rather than hidden: the user picked something specific and is
 * entitled to know why it will not open.
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

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

const push = vi.fn();
vi.mock('next/navigation', async (importOriginal) => ({
  ...(await importOriginal<typeof import('next/navigation')>()),
  useRouter: () => ({ push }),
  usePathname: () => '/scm/sales-orders',
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

let hasPermission = true;
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => hasPermission,
  usePermissions: () => ({ permissions: [], permissionSet: new Set(), isLoading: false }),
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
import type { SalesOrder, SalesOrderInquiry } from '../../types/scm.types';

function inquiry(over: Partial<SalesOrderInquiry> = {}): SalesOrderInquiry {
  return {
    inquiry_no: 'OI-000001',
    state: 'raised',
    raised_at: '2026-07-02T09:00:00',
    raised_by_name: 'Yana',
    rows_total: 4,
    rows_placed: 1,
    ...over,
  };
}

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
    stock_locations: [],
    linked_purchase_orders: [],
    awaiting_purchase_orders: 0,
    order_inquiries: [],
    created_at: '2026-07-01T00:00:00',
    ...over,
  } as SalesOrder;
}

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
    data: {
      data: rows,
      pagination: { total: rows.length, page: 1, limit: 50 },
      empty: !rows.length,
    },
    isLoading: false,
    isFetching: false,
    refetch: vi.fn(),
  });
}

beforeEach(() => {
  push.mockReset();
  hasPermission = true;
});

// ── the Order inquiries column ──────────────────────────────────────────────

describe('SalesOrdersList - Order inquiries column', () => {
  it('names each inquiry and links it to the worklist for that order', async () => {
    stub([order({ order_inquiries: [inquiry()] })]);
    renderList();

    const link = await screen.findByRole('link', { name: 'OI-000001' });
    expect(link).toHaveAttribute(
      'href',
      '/project-sales/order-inquiries?query=SO900001',
    );
  });

  it('says who raised each one and how far purchasing has got, on the title', async () => {
    // The cell stays a row of numbers - the detail is what a hover is for, exactly as the
    // "Waiting on" column already does it.
    stub([order({ order_inquiries: [inquiry()] })]);
    renderList();

    const link = await screen.findByRole('link', { name: 'OI-000001' });
    const cell = link.closest('span[title]');
    expect(cell?.getAttribute('title')).toContain('by Yana');
    expect(cell?.getAttribute('title')).toContain('1/4 placed');
  });

  it('caps the list at two and counts the rest', async () => {
    stub([
      order({
        order_inquiries: [
          inquiry({ inquiry_no: 'OI-000001' }),
          inquiry({ inquiry_no: 'OI-000002' }),
          inquiry({ inquiry_no: 'OI-000003' }),
        ],
      }),
    ]);
    renderList();

    expect(await screen.findByRole('link', { name: 'OI-000001' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'OI-000002' })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'OI-000003' })).toBeNull();
    expect(screen.getByText('+1 more')).toBeInTheDocument();
  });

  it('reads "-" for an order nobody has planned, rather than an empty cell', async () => {
    stub([order({ order_inquiries: [] })]);
    renderList();

    await screen.findByText('SO900001');
    expect(screen.queryByRole('link', { name: /^OI-/ })).toBeNull();
    expect(screen.getAllByText('-').length).toBeGreaterThan(0);
  });
});

// ── selection + Plan ────────────────────────────────────────────────────────

describe('SalesOrdersList - planning the selected orders', () => {
  const rows = (n: number) =>
    Array.from({ length: n }, (_, i) =>
      order({ id: `so-${i}`, so_number: `SO90000${i}` }),
    );

  async function selectAll() {
    const all = await screen.findByLabelText('Select all rows on this page');
    fireEvent.click(all);
  }

  /**
   * Open the toolbar's Start dropdown (A1/A3: Plan selected moved off the Actions menu and
   * onto Start, beside Upload sales orders - the two ways a day's work begins). Radix opens
   * on pointerdown, which jsdom does not synthesise from `fireEvent.click`, so the keyboard
   * opens it instead.
   */
  async function openStart() {
    const trigger = await screen.findByRole('button', { name: /^Start$/ });
    fireEvent.keyDown(trigger, { key: 'Enter' });
  }

  it('opens the board on the ticked orders, by document number', async () => {
    stub(rows(2));
    renderList();

    fireEvent.click(await screen.findByLabelText('Select SO900000'));
    await openStart();
    fireEvent.click(screen.getByRole('menuitem', { name: /^Plan selected \(1\)$/ }));

    expect(push).toHaveBeenCalledWith(
      '/project-sales/fulfilment-planning?orders=SO900000',
    );
  });

  it('counts the whole selection in the label', async () => {
    stub(rows(3));
    renderList();
    await selectAll();

    await openStart();
    fireEvent.click(screen.getByRole('menuitem', { name: /^Plan selected \(3\)$/ }));

    expect(push).toHaveBeenCalledWith(
      '/project-sales/fulfilment-planning?orders=SO900000%2CSO900001%2CSO900002',
    );
  });

  it('is offered before anything is ticked, disabled, saying what it wants', async () => {
    // The bug: in the bulk strip this action did not exist until rows were selected, so
    // the menu never taught that the orders are picked on the rows.
    stub(rows(2));
    renderList();

    await openStart();
    const item = screen.getByRole('menuitem', { name: /^Plan selected \(0\)$/ });
    expect(item).toHaveAttribute('data-disabled');
    expect(item).toHaveAttribute('title', expect.stringContaining('Tick the sales orders'));
    fireEvent.click(item);
    expect(push).not.toHaveBeenCalled();
  });

  it('refuses more than the board can hold, and says so on the item', async () => {
    stub(rows(51));
    renderList();
    await selectAll();

    await openStart();
    const item = screen.getByRole('menuitem', { name: /^Plan selected \(51\)$/ });
    expect(item).toHaveAttribute('data-disabled');
    expect(item).toHaveAttribute('title', expect.stringContaining('up to 50'));
    fireEvent.click(item);
    expect(push).not.toHaveBeenCalled();
  });

  it('leaves the bulk strip to the count, Export and Clear', async () => {
    stub(rows(2));
    renderList();
    await selectAll();

    await waitFor(() => expect(screen.getByText('2 selected')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: 'Export' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Clear' })).toBeInTheDocument();
    // No Plan BUTTON anywhere: the only one is the menu item, which is not open.
    expect(screen.queryByRole('button', { name: /^Plan/ })).toBeNull();
  });

  it('offers nothing at all without the permission the board itself requires', async () => {
    hasPermission = false;
    stub(rows(2));
    renderList();
    await selectAll();

    await waitFor(() => expect(screen.getByText('2 selected')).toBeInTheDocument());
    await openStart();
    expect(screen.queryByRole('menuitem', { name: /^Plan selected/ })).toBeNull();
  });
});

// ── the Changed badge (AC-P3-1) ─────────────────────────────────────────────

describe('SalesOrdersList - the Changed badge', () => {
  it('opens the board on this order and its batch', async () => {
    stub([order({ planning_change_batch_id: 'pcb-so381895' })]);
    renderList();

    const badge = await screen.findByTestId('so-changed-SO900001');
    expect(badge).toHaveTextContent('Changed');
    expect(badge).toHaveAttribute(
      'href',
      '/project-sales/fulfilment-planning?orders=SO900001&batch=pcb-so381895',
    );
  });

  it('is absent on an order with nothing outstanding to apply', async () => {
    stub([order({})]);
    renderList();

    await screen.findByText('SO900001');
    expect(screen.queryByTestId('so-changed-SO900001')).toBeNull();
  });
});
