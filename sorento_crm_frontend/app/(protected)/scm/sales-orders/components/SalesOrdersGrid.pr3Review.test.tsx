/**
 * FILTER-MULTISELECT PR3 review: an agent id the options do not hold (a saved view from before the agent was
 * removed, or before the agent options load) is never shown as its own label: no UUID in the Agent trigger or
 * the chip. Uses the real SearchableMultiSelect; harness mirrors SalesOrdersGrid.multiFilters.test.tsx.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
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
Element.prototype.scrollIntoView = vi.fn();

const push = vi.fn();
// Mutable per test: `useListStateFromUrl` reads this to restore pagination/search from a
// Back-to-list query string (S3-01). Empty by default - a fresh sidebar-click open.
const nav = vi.hoisted(() => ({ search: '' }));
vi.mock('next/navigation', async (importOriginal) => ({
  ...(await importOriginal<typeof import('next/navigation')>()),
  useRouter: () => ({ push }),
  usePathname: () => '/scm/sales-orders',
  useSearchParams: () => new URLSearchParams(nav.search),
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

const service = vi.hoisted(() => ({
  getUserListColumnConfig: vi.fn(),
  upsertUserListColumnConfig: vi.fn(),
}));
vi.mock('@/lib/listing-column-preferences/listColumnPreferencesService', () => ({
  getUserListColumnConfig: (...a: unknown[]) => service.getUserListColumnConfig(...a),
  upsertUserListColumnConfig: (...a: unknown[]) => service.upsertUserListColumnConfig(...a),
  resetUserListColumnConfig: vi.fn(async () => undefined),
}));

vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => true,
  usePermissions: () => ({ permissions: [], permissionSet: new Set(), isLoading: false }),
}));

const EMPTY = { data: [], isLoading: false };
// Mutable per test: the customer master is a multi-thousand-row list that resolves later
// than the grid's own first paint, so a test needs to simulate "not resolved yet".
const customerOptionsResult = vi.hoisted(() => ({
  data: [{ value: 'C001', label: 'Acme Kitchens' }] as { value: string; label: string }[],
  isLoading: false,
}));
vi.mock('../../hooks/useScmOptions', () => ({
  useCustomerOptions: () => customerOptionsResult,
  useOrderTypeOptions: () => EMPTY,
  useProductOptions: () => EMPTY,
  useSupplierOptions: () => EMPTY,
  useCategoryOptions: () => EMPTY,
  useWarehouseOptions: () => EMPTY,
}));

vi.mock('../hooks/useSalesAgentOptions', () => ({
  useSalesAgentOptions: () => ({
    options: [{ value: 'AG1', label: 'SEAN I' }],
    isLoading: false,
  }),
}));

// The standard SearchableSelect, stood in for as a native <select> - the same pattern
// `SalesOrdersGrid.test.tsx` uses - so a filter change is one `fireEvent.change` rather than
// driving a cmdk popover. What is under test here is the remembered-view wiring, not the
// popover mechanics.
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    id,
    value,
    onChange,
    options = [],
    placeholder,
  }: {
    id?: string;
    value?: string;
    onChange?: (v: string) => void;
    options?: Array<{ value: string; label: string }>;
    placeholder?: string;
  }) => (
    <select
      id={id}
      aria-label={placeholder}
      value={value}
      onChange={(e) => onChange?.(e.target.value)}
    >
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));


const hooks = vi.hoisted(() => ({ useSalesOrders: vi.fn() }));
vi.mock('../../hooks/useSalesOrders', () => ({
  useSalesOrders: (...a: unknown[]) => hooks.useSalesOrders(...a),
  useSalesOrderAgents: () => ({ data: [], isLoading: false }),
  useCreateSalesOrder: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdateSalesOrder: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useDeleteSalesOrder: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useResetSalesOrderPlanning: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useCreateDoFromSalesOrder: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

import SalesOrdersGrid from './SalesOrdersGrid';
import type { SalesOrder } from '../../types/scm.types';

const LISTING_KEY = '/scm/sales-orders';

type ListParams = Record<string, unknown> & { enabled: boolean };

function storedConfig(config: Record<string, unknown> | null) {
  service.getUserListColumnConfig.mockResolvedValue({ listing_key: LISTING_KEY, config });
  service.upsertUserListColumnConfig.mockImplementation(async (listingKey: string, payload: unknown) => ({
    listing_key: listingKey,
    config: payload,
  }));
}

function order(): SalesOrder {
  return {
    id: 'so-1', so_number: 'SO900001', order_type: 'project', order_type_label: 'Project', customer_code: 'C001',
    customer_name: 'Acme Kitchens', market_segment: null, priority: 'normal', status: 'open', order_date: '2026-07-01',
    requested_delivery_date: '2026-09-01', total_qty: 12, committed_qty: 12, lines: [], source: 'upload',
    stock_locations: [], linked_purchase_orders: [], awaiting_purchase_orders: 0, order_inquiries: [],
    created_at: '2026-07-01T00:00:00',
  } as SalesOrder;
}

function mockList() {
  hooks.useSalesOrders.mockImplementation((params: ListParams) => ({
    data: params?.enabled
      ? { data: [order()], pagination: { total: 1, page: 1, limit: 25 }, empty: false }
      : undefined,
    isLoading: false, isFetching: false, refetch: vi.fn(),
  }));
}

function renderGrid() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SalesOrdersGrid />
    </QueryClientProvider>,
  );
}

const lastParams = () => {
  const calls = hooks.useSalesOrders.mock.calls.map((c) => c[0] as ListParams).filter((p) => p.enabled);
  return calls[calls.length - 1];
};

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  nav.search = '';
  customerOptionsResult.data = [
    { value: 'C001', label: 'Acme Kitchens' },
    { value: 'C002', label: 'Beta Baths' },
  ];
  customerOptionsResult.isLoading = false;
  mockList();
});

async function openFilters(user: ReturnType<typeof userEvent.setup>) {
  renderGrid();
  await screen.findByText('SO900001');
  await user.click(screen.getByRole('button', { name: /^filters/i }));
}
const UUID = /[0-9a-f]{8}-[0-9a-f]{4}-/i;
const ORPHAN = '9f1b6c52-4d1e-4a39-8a77-0c2d5e8b1f34';

describe('Sales orders - an agent id the options do not hold', () => {
  it('shows no UUID in the Agent trigger or a chip when a saved view holds it', async () => {
    storedConfig({
      version: 1,
      sorting: [{ id: 'so_number', desc: false }],
      filters: { sales_agent_id: ORPHAN },
      filtersVersion: 2,
    });
    const user = userEvent.setup();
    await openFilters(user);
    await waitFor(() => expect(lastParams().salesAgentId).toBe(ORPHAN));
    expect(document.body.textContent ?? '').not.toMatch(UUID);
  });

  it('shows no UUID beside a known agent either', async () => {
    storedConfig({
      version: 1,
      sorting: [{ id: 'so_number', desc: false }],
      filters: { sales_agent_id: `AG1,${ORPHAN}` },
      filtersVersion: 2,
    });
    const user = userEvent.setup();
    await openFilters(user);
    await waitFor(() => expect(lastParams().salesAgentId).toBe(`AG1,${ORPHAN}`));
    expect(document.body.textContent ?? '').not.toMatch(UUID);
    expect(document.body.textContent ?? '').toMatch(/SEAN I/);
  });
});
