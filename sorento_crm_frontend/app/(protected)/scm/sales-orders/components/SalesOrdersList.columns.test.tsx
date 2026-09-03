/**
 * What the two money-and-date columns on the sales-order list actually print.
 *
 * **Delivery date** is a compilation of the LINE dates (`sales_order_lines.required_date`),
 * not the header's `requested_delivery_date`: one order routinely ships across two dates,
 * and the header figure is blank on most of this book. One date when the lines agree, a
 * range when they do not, "-" when no line names one. The header figure keeps its place on
 * the detail page, so nothing is lost by the list no longer showing it.
 *
 * **Total amount** is the order's own total, through the same formatter the detail page's
 * Totals card uses, so the two screens cannot disagree about what an order is worth. "-"
 * and not "RM 0" when nobody priced it.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
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

vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => true,
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
import type { SalesOrder } from '../../types/scm.types';

function order(over: Partial<SalesOrder> = {}): SalesOrder {
  return {
    id: 'so-1',
    so_number: 'SO900001',
    order_type: 'project',
    order_type_label: 'Project',
    customer_code: 'CUS-1',
    customer_name: 'Acme Kitchens',
    market_segment: null,
    priority: 'normal',
    status: 'open',
    order_date: '2026-07-01',
    requested_delivery_date: '2026-09-01',
    total_qty: 12,
    committed_qty: 12,
    lines: [],
    source: 'upload',
    stock_locations: [],
    linked_purchase_orders: [],
    awaiting_purchase_orders: 0,
    order_inquiries: [],
    created_at: '2026-07-01T00:00:00',
    ...over,
  } as SalesOrder;
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

function renderList() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <SalesOrdersList />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  push.mockReset();
});

describe('SalesOrdersList - Delivery date column', () => {
  it('is headed "Delivery date", not "Requested delivery"', async () => {
    stub([order({ delivery_dates: ['2026-01-12'] })]);
    renderList();

    expect(await screen.findByText('Delivery date')).toBeInTheDocument();
    expect(screen.queryByText('Requested delivery')).toBeNull();
  });

  it('prints ONE date, and no expander, when every dated line falls on the same day', async () => {
    stub([order({ delivery_dates: ['2026-01-12'] })]);
    renderList();

    expect(await screen.findByText('12/01/2026')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /delivery dates/ })).toBeNull();
  });

  it('prints the earliest and offers the rest, never a range', async () => {
    // A range would claim the eight weeks between the two dates. The order is due on two
    // DAYS, so the cell names the first and puts the others one click away - and the row
    // keeps its size whether the order is due on one day or on nine.
    stub([order({ delivery_dates: ['2026-01-12', '2026-03-10'] })]);
    renderList();

    expect(await screen.findByText('12/01/2026')).toBeInTheDocument();
    expect(screen.queryByText('12/01/2026 - 10/03/2026')).toBeNull();
    expect(
      screen.getByRole('button', { name: 'Show all 2 delivery dates' }),
    ).toHaveTextContent('+1');
  });

  it('lists every distinct date when the expander is opened', async () => {
    stub([order({ delivery_dates: ['2026-01-12', '2026-02-04', '2026-03-10'] })]);
    renderList();

    fireEvent.click(await screen.findByRole('button', { name: 'Show all 3 delivery dates' }));

    expect(await screen.findByText('04/02/2026')).toBeInTheDocument();
    expect(screen.getByText('10/03/2026')).toBeInTheDocument();
  });

  it('opening the dates does not open the order', async () => {
    stub([order({ delivery_dates: ['2026-01-12', '2026-03-10'] })]);
    renderList();

    fireEvent.click(await screen.findByRole('button', { name: 'Show all 2 delivery dates' }));

    expect(push).not.toHaveBeenCalled();
  });

  it('reads "-" when no line names a delivery date', async () => {
    // Even though the HEADER carries `requested_delivery_date` - which this column
    // deliberately no longer shows, since it is a different figure.
    stub([
      order({
        requested_delivery_date: '2026-09-01',
        delivery_dates: [],
      }),
    ]);
    renderList();

    await screen.findByText('SO900001');
    expect(screen.queryByText('01/09/2026')).toBeNull();
    expect(screen.getAllByText('-').length).toBeGreaterThan(0);
  });
});

describe('SalesOrdersList - Total amount column', () => {
  it('prints the order total in ringgit', async () => {
    stub([order({ total_amount: '31985.00' })]);
    renderList();

    expect(await screen.findByText('RM 31,985.00')).toBeInTheDocument();
  });

  it('reads "-" for an order nobody priced, never RM 0', async () => {
    stub([order({ total_amount: null })]);
    renderList();

    await screen.findByText('SO900001');
    expect(screen.queryByText(/^RM /)).toBeNull();
    expect(screen.getAllByText('-').length).toBeGreaterThan(0);
  });
});
