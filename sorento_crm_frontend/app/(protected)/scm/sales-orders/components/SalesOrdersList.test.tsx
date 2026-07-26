/**
 * SCM AutoCount mirror — Slice 8. SalesOrdersList read-only gate.
 *   - an AutoCount SO row shows the AutoCount badge and offers ONLY a read-only
 *     View action (no Create DO / Edit / Delete)
 *   - a native (manual) SO row keeps its full mutating action set and no badge
 *   - loading state renders a skeleton
 *
 * Data + mutation hooks are mocked; the form modal is stubbed so the list is
 * assertable without the modal's option queries / QueryClient.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render as rtlRender, screen, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}
Element.prototype.scrollIntoView = vi.fn();

vi.mock('next/navigation', () => ({
  usePathname: () => '/scm/sales-orders',
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

// Stub the form modal — its option hooks need a QueryClient we don't provide.
vi.mock('./SalesOrderFormModal', () => ({
  SalesOrderFormModal: () => null,
}));

const useSalesOrders = vi.fn();
const noopMut = { mutateAsync: vi.fn(), isPending: false };
vi.mock('../../hooks/useSalesOrders', () => ({
  useSalesOrders: (...a: unknown[]) => useSalesOrders(...a),
  useCreateSalesOrder: () => noopMut,
  useUpdateSalesOrder: () => noopMut,
  useDeleteSalesOrder: () => noopMut,
  useCreateDoFromSalesOrder: () => noopMut,
}));

import SalesOrdersList from './SalesOrdersList';
import type { SalesOrder } from '../../types/scm.types';

function render(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return rtlRender(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

function so(over: Partial<SalesOrder>): SalesOrder {
  return {
    id: 'so-1',
    so_number: 'SO-2026/07-0001',
    order_type: 'standard',
    order_type_label: 'Standard',
    customer_code: 'CUST-1',
    customer_name: 'Acme Retail',
    market_segment: null,
    priority: 'normal',
    status: 'open',
    order_date: '2026-07-16',
    requested_delivery_date: null,
    total_qty: 12,
    committed_qty: 12,
    lines: [],
    created_at: '2026-07-16T00:00:00',
    source: 'manual',
    source_doc_no: null,
    internal_note: null,
    follow_up: false,
    ...over,
  } as SalesOrder;
}

function mockList(rows: SalesOrder[], over: Record<string, unknown> = {}) {
  useSalesOrders.mockReturnValue({
    data: { data: rows, pagination: { page: 1, total: rows.length } },
    isLoading: false,
    isFetching: false,
    refetch: vi.fn(),
    ...over,
  });
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('SalesOrdersList — states', () => {
  it('renders the loading skeleton state', () => {
    useSalesOrders.mockReturnValue({ data: undefined, isLoading: true, isFetching: true, refetch: vi.fn() });
    const { container } = render(<SalesOrdersList />);
    expect(container.querySelector('[data-slot="skeleton"], .animate-pulse')).toBeTruthy();
  });
});

describe('SalesOrdersList — AutoCount mirror rows (read-only gate, Slice 8)', () => {
  it('shows the AutoCount badge and only a View action on an autocount SO', () => {
    mockList([so({ id: 'so-ac', so_number: 'AC-SMOKE-SO-1', source: 'autocount' })]);
    render(<SalesOrdersList />);
    expect(screen.getByText('AC-SMOKE-SO-1')).toBeInTheDocument();
    expect(screen.getByText('AutoCount')).toBeInTheDocument();
    // Read-only: a View action, and NONE of the mutating affordances.
    expect(screen.getByRole('button', { name: /View/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Create DO/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /^Edit$/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /^Delete$/i })).toBeNull();
  });

  it('keeps the full mutating action set and no badge on a native SO', () => {
    mockList([so({ id: 'so-native', so_number: 'SO-2026/07-0002', source: 'manual' })]);
    render(<SalesOrdersList />);
    expect(screen.queryByText('AutoCount')).toBeNull();
    expect(screen.getByRole('button', { name: /Create DO/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^Edit$/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^Delete$/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /View/i })).toBeNull();
  });
});
