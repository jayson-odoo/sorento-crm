/**
 * Reset planning (the captain, 27 Aug 2026): a UAT walk has to be repeatable from the
 * screen. Tick the orders, Actions > "Reset planning (N)", confirm - and the order is back
 * to never planned. Confirmed like a delete, because it is one.
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
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn(), custom: vi.fn() },
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
const resetPlanning = vi.fn(async () => ({ so_number: 'SO900000', planned: true, removed: {} }));
vi.mock('../../hooks/useSalesOrders', () => ({
  useSalesOrders: (...a: unknown[]) => useSalesOrders(...a),
  useSalesOrderAgents: () => ({ data: [], isLoading: false }),
  useCreateSalesOrder: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdateSalesOrder: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useDeleteSalesOrder: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useResetSalesOrderPlanning: () => ({ mutateAsync: resetPlanning, isPending: false }),
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

async function openActions() {
  const trigger = await screen.findByRole('button', { name: /Actions/i });
  fireEvent.keyDown(trigger, { key: 'Enter' });
}

beforeEach(() => {
  resetPlanning.mockClear();
  hasPermission = true;
});

describe('SalesOrdersList - Reset planning', () => {
  const rows = [
    order({ id: 'so-0', so_number: 'SO900000' }),
    order({ id: 'so-1', so_number: 'SO900001' }),
  ];

  it('is offered disabled before anything is ticked', async () => {
    stub(rows);
    renderList();
    await openActions();
    const item = screen.getByRole('menuitem', { name: /^Reset planning \(0\)$/ });
    expect(item).toHaveAttribute('aria-disabled', 'true');
  });

  it('confirms, names the orders, and resets each ticked one', async () => {
    stub(rows);
    renderList();
    fireEvent.click(await screen.findByLabelText('Select SO900000'));
    await openActions();
    fireEvent.click(screen.getByRole('menuitem', { name: /^Reset planning \(1\)$/ }));

    expect(await screen.findByRole('dialog')).toHaveTextContent('SO900000');
    expect(resetPlanning).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Reset planning' }));
    await waitFor(() => expect(resetPlanning).toHaveBeenCalledTimes(1));
    expect(resetPlanning).toHaveBeenCalledWith({ id: 'so-0', rewindBook: false });
  });

  it('carries the rewind-book tick through', async () => {
    stub(rows);
    renderList();
    fireEvent.click(await screen.findByLabelText('Select SO900001'));
    await openActions();
    fireEvent.click(screen.getByRole('menuitem', { name: /^Reset planning \(1\)$/ }));
    fireEvent.click(await screen.findByRole('checkbox', { name: /before the first upload/i }));
    fireEvent.click(screen.getByRole('button', { name: 'Reset planning' }));
    await waitFor(() => expect(resetPlanning).toHaveBeenCalledWith({ id: 'so-1', rewindBook: true }));
  });

  it('is not offered without the write permission', async () => {
    hasPermission = false;
    stub(rows);
    renderList();
    await openActions();
    expect(screen.queryByRole('menuitem', { name: /Reset planning/ })).not.toBeInTheDocument();
  });
});
