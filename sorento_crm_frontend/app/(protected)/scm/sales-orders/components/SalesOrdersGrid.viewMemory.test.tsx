/**
 * SCM Sales Orders - remembered view (PLAN-listing-view-memory, rollout: SCM Sales Orders).
 *
 * Mirrors `StockInquiriesList.viewMemory.test.tsx`, the pilot's own suite: the grid renders
 * with the REAL `useListingViewPreferences`; only the preferences transport, the data hook
 * and the option hooks are stubbed. This pins the pieces the unit tests cannot see together:
 * - the data query is held until the stored view resolves and then fires ONCE, already
 *   sorted (latest Document date first, the shipped default) and filtered (AC-B2/AC-B3);
 * - a restored filter is stated as a chip above the grid, by NAME never by raw id, and its
 *   Clear drops the filter, refetches unfiltered and writes an explicit null (AC-C1/AC-C2);
 * - a blob from an older `filtersVersion` is discarded while the sort is kept (AC-B4);
 * - changing the sort or a filter debounce-writes it (AC-B5/AC-B6), never page or search
 *   (AC-D1/AC-D2);
 * - a pinned sales agent wins over a stored `sales_agent_id`, which never reaches the chip.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react';
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

type ListParams = {
  pageIndex: number;
  pageSize: number;
  sorting: { id: string; desc: boolean }[];
  searchQuery: string;
  status: string | null;
  customerCode: string | null;
  outstanding: boolean;
  salesAgentId: string | null;
  enabled: boolean;
};

function storedConfig(config: Record<string, unknown> | null) {
  service.getUserListColumnConfig.mockResolvedValue({
    listing_key: LISTING_KEY,
    config,
  });
  service.upsertUserListColumnConfig.mockImplementation(
    async (listingKey: string, payload: unknown) => ({
      listing_key: listingKey,
      config: payload,
    }),
  );
}

function order(over: Partial<SalesOrder> = {}): SalesOrder {
  return {
    id: 'so-1',
    so_number: 'SO900001',
    order_type: 'project',
    order_type_label: 'Project',
    customer_code: 'C001',
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

function mockList(rows: SalesOrder[]) {
  hooks.useSalesOrders.mockReturnValue({
    data: {
      data: rows,
      pagination: { total: rows.length, page: 1, limit: 25 },
      empty: rows.length === 0,
    },
    isLoading: false,
    isFetching: false,
    refetch: vi.fn(),
  });
}

function renderGrid(props: { salesAgentId?: string } = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SalesOrdersGrid {...props} />
    </QueryClientProvider>,
  );
}

/** Every set of params the data hook was asked to fetch with (`enabled: true`). */
function enabledFetches(): ListParams[] {
  return hooks.useSalesOrders.mock.calls
    .map((c) => c[0] as ListParams)
    .filter((p) => p.enabled);
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  nav.search = '';
  customerOptionsResult.data = [{ value: 'C001', label: 'Acme Kitchens' }];
  customerOptionsResult.isLoading = false;
});

afterEach(() => {
  vi.useRealTimers();
});

describe('SalesOrdersGrid remembered view', () => {
  it('holds the fetch, then fires once with the shipped default (latest Document date first, no filter) with nothing stored (AC-B2)', async () => {
    storedConfig(null);
    mockList([order()]);
    renderGrid();

    expect(
      (hooks.useSalesOrders.mock.calls[0][0] as ListParams).enabled,
    ).toBe(false);

    expect(await screen.findByText('SO900001')).toBeInTheDocument();

    const fetched = enabledFetches();
    expect(fetched.length).toBeGreaterThan(0);
    for (const p of fetched) {
      expect(p.sorting).toEqual([{ id: 'order_date', desc: true }]);
      expect(p.status).toBeNull();
    }
    expect(
      screen.queryByRole('button', { name: /^Clear filter:/ }),
    ).not.toBeInTheDocument();

    // No write before the user has changed anything.
    await new Promise((r) => setTimeout(r, 1000));
    expect(service.upsertUserListColumnConfig).not.toHaveBeenCalled();
  });

  it('every enabled fetch carries the stored sort and filters, and states them on the chip by name (AC-B3 / AC-C1)', async () => {
    storedConfig({
      version: 1,
      sorting: [{ id: 'so_number', desc: false }],
      filters: { status: 'open', customer_code: 'C001', outstanding: true },
      filtersVersion: 2,
    });
    mockList([order()]);
    renderGrid();

    expect(await screen.findByText('SO900001')).toBeInTheDocument();

    const fetched = enabledFetches();
    expect(fetched.length).toBeGreaterThan(0);
    for (const p of fetched) {
      expect(p.sorting).toEqual([{ id: 'so_number', desc: false }]);
      expect(p.status).toBe('open');
      expect(p.customerCode).toBe('C001');
      expect(p.outstanding).toBe(true);
    }

    const clear = await screen.findByRole('button', { name: /^Clear filter:/ });
    const chipText = clear.closest('span')?.textContent ?? '';
    // Named the status and the customer, never the raw code the customer filter is stored as.
    expect(chipText).toContain('Acme Kitchens');
    expect(chipText).toContain('Outstanding qty');
    expect(chipText).not.toContain('C001');
  });

  it('falls back to the axis word while the customer name has not resolved yet, never a blank chip', async () => {
    // The normal first paint for a user with only a customer filter remembered: the
    // multi-thousand-row customer master has not answered yet.
    customerOptionsResult.data = [];
    storedConfig({
      version: 1,
      sorting: [{ id: 'order_date', desc: true }],
      filters: { customer_code: 'C001' },
      filtersVersion: 2,
    });
    mockList([order()]);
    renderGrid();

    const clear = await screen.findByRole('button', { name: 'Clear filter: Customer' });
    expect(clear.closest('span')?.textContent).toBe('Customer');
    expect(clear.closest('span')?.textContent).not.toContain('C001');
  });

  it('discards a filter blob written by an older page shape but keeps the sort (AC-B4)', async () => {
    storedConfig({
      version: 1,
      sorting: [{ id: 'so_number', desc: false }],
      // A key this shape DOES read, under a version the shipped one is not - so a broken
      // gate would surface as a real, visible bug (a chip and a filtered fetch), not as a
      // test that stays green whether or not the gate runs.
      filters: { status: 'open' },
      filtersVersion: 1,
    });
    mockList([order()]);
    renderGrid();

    expect(await screen.findByText('SO900001')).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: /^Clear filter:/ }),
    ).not.toBeInTheDocument();

    const last = enabledFetches().at(-1)!;
    expect(last.sorting).toEqual([{ id: 'so_number', desc: false }]);
    expect(last.status).toBeNull();

    await new Promise((r) => setTimeout(r, 1000));
    expect(service.upsertUserListColumnConfig).not.toHaveBeenCalled();
  });

  it('writes a changed filter after the debounce, carrying no page or search key (AC-B6 / AC-D1 / AC-D2)', async () => {
    storedConfig(null);
    mockList([order()]);
    renderGrid();
    await screen.findByText('SO900001');

    fireEvent.keyDown(await screen.findByRole('button', { name: /Filters/i }), {
      key: 'Enter',
    });
    const statusSelect = await screen.findByRole('combobox', { name: /status/i });

    vi.useFakeTimers();
    fireEvent.change(statusSelect, { target: { value: 'open' } });
    await vi.advanceTimersByTimeAsync(900);
    vi.useRealTimers();

    expect(service.upsertUserListColumnConfig).toHaveBeenCalled();
    const [key, payload] = service.upsertUserListColumnConfig.mock.calls.at(-1)!;
    expect(key).toBe(LISTING_KEY);
    expect(payload).toMatchObject({ filters: { status: 'open' } });
    expect(payload).not.toHaveProperty('page');
    expect(payload).not.toHaveProperty('query');
    expect(payload).not.toHaveProperty('pageIndex');
    expect(payload).not.toHaveProperty('searchQuery');
  });

  it('writes a changed sort after the debounce (AC-B5)', async () => {
    storedConfig(null);
    mockList([order()]);
    renderGrid();
    await screen.findByText('SO900001');

    vi.useFakeTimers();
    fireEvent.click(screen.getByRole('button', { name: 'SO number' }));
    await vi.advanceTimersByTimeAsync(900);
    vi.useRealTimers();

    expect(service.upsertUserListColumnConfig).toHaveBeenCalled();
    const [, payload] = service.upsertUserListColumnConfig.mock.calls.at(-1)!;
    expect(payload.sorting).toEqual([{ id: 'so_number', desc: false }]);
  });

  it("the chip's Clear drops the filter, refetches unfiltered and writes an explicit null (AC-C2)", async () => {
    storedConfig({
      version: 1,
      sorting: [{ id: 'order_date', desc: true }],
      filters: { status: 'open' },
      filtersVersion: 2,
    });
    mockList([order()]);
    renderGrid();

    const clear = await screen.findByRole('button', { name: /^Clear filter:/ });
    fireEvent.click(clear);

    await waitFor(() => {
      expect(
        screen.queryByRole('button', { name: /^Clear filter:/ }),
      ).not.toBeInTheDocument();
    });
    const last = enabledFetches().at(-1)!;
    expect(last.status).toBeNull();
    expect(last.pageIndex).toBe(0);

    await waitFor(
      () => {
        expect(service.upsertUserListColumnConfig).toHaveBeenCalled();
      },
      { timeout: 3000 },
    );
    const [, payload] = service.upsertUserListColumnConfig.mock.calls.at(-1)!;
    expect(payload).toMatchObject({ filters: null, filtersVersion: null });
    expect(payload.sorting).toEqual([{ id: 'order_date', desc: true }]);
  });

  it('a pinned sales agent wins over a stored sales_agent_id, and the chip never mentions it', async () => {
    storedConfig({
      version: 1,
      sorting: [{ id: 'order_date', desc: true }],
      filters: { sales_agent_id: 'AG1' },
      filtersVersion: 2,
    });
    mockList([order()]);
    renderGrid({ salesAgentId: 'agent-pin' });

    expect(await screen.findByText('SO900001')).toBeInTheDocument();

    const fetched = enabledFetches();
    expect(fetched.length).toBeGreaterThan(0);
    for (const p of fetched) {
      expect(p.salesAgentId).toBe('agent-pin');
    }
    // The stored agent never contributes an axis to the chip while pinned - so, with no
    // other filter stored, no chip renders at all.
    expect(
      screen.queryByRole('button', { name: /^Clear filter:/ }),
    ).not.toBeInTheDocument();
  });

  it('Back to sales orders restores the page it carries, not page 1 (S3-01 vs the search reset effect)', async () => {
    // The detail page's Back button hands the list its own query string back
    // (`useListStateFromUrl`). Page 3 must survive the mount, not be wiped by the
    // search-reset effect firing once on its own first run.
    nav.search = 'page=3&limit=25&sort=order_date&dir=desc';
    storedConfig(null);
    mockList([order()]);
    renderGrid();

    expect(await screen.findByText('SO900001')).toBeInTheDocument();

    const fetched = enabledFetches();
    expect(fetched.length).toBeGreaterThan(0);
    expect(fetched[0].pageIndex).toBe(2);
  });
});
