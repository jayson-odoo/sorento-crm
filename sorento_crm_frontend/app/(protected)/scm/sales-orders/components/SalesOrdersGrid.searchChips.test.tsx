/**
 * SEARCH-CHIPS slice 1 (UAC S1-S4): the Sales orders list's search box in chips mode.
 *
 * Mocking mirrors `SalesOrdersGrid.viewMemory.test.tsx`, with one difference: the REAL
 * `useSalesOrders` -> `getSalesOrders` -> `buildDataGridParams` chain runs and only
 * `apiFetch` is stubbed, so the assertions read the actual list GET URL the browser would send.
 * - S1: chips + typed text reach the request as one `query` param each;
 * - S2: a list URL carrying two `query` params (Back from a record) restores two chips;
 * - S3: adding a chip returns to page 1, sort kept;
 * - S4: adding a chip writes the query params into the address bar (`history.replaceState`).
 * Red first: `ListSearchInput` has no chips mode and the grid sends one `query`.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
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
const nav = vi.hoisted(() => ({ search: '' }));
vi.mock('next/navigation', async (importOriginal) => ({
  ...(await importOriginal<typeof import('next/navigation')>()),
  useRouter: () => ({ push, replace: vi.fn() }),
  usePathname: () => '/scm/sales-orders',
  useSearchParams: () => new URLSearchParams(nav.search),
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

const prefs = vi.hoisted(() => ({
  getUserListColumnConfig: vi.fn(),
  upsertUserListColumnConfig: vi.fn(),
}));
vi.mock('@/lib/listing-column-preferences/listColumnPreferencesService', () => ({
  getUserListColumnConfig: (...a: unknown[]) => prefs.getUserListColumnConfig(...a),
  upsertUserListColumnConfig: (...a: unknown[]) => prefs.upsertUserListColumnConfig(...a),
  resetUserListColumnConfig: vi.fn(async () => undefined),
}));

vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => true,
  usePermissions: () => ({ permissions: [], permissionSet: new Set(), isLoading: false }),
}));

const EMPTY = { data: [], isLoading: false };
vi.mock('../../hooks/useScmOptions', () => ({
  useCustomerOptions: () => ({ data: [{ value: 'C001', label: 'Acme Kitchens' }], isLoading: false }),
  useOrderTypeOptions: () => EMPTY,
  useProductOptions: () => EMPTY,
  useSupplierOptions: () => EMPTY,
  useCategoryOptions: () => EMPTY,
  useWarehouseOptions: () => EMPTY,
}));

vi.mock('../hooks/useSalesAgentOptions', () => ({
  useSalesAgentOptions: () => ({ options: [{ value: 'AG1', label: 'SEAN I' }], isLoading: false }),
}));

// The real list hook (and through it the real service + `buildDataGridParams`); the rest stubbed.
vi.mock('../../hooks/useSalesOrders', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../hooks/useSalesOrders')>();
  return {
    ...actual,
    useSalesOrderAgents: () => ({ data: [], isLoading: false }),
    useCreateSalesOrder: () => ({ mutateAsync: vi.fn(), isPending: false }),
    useUpdateSalesOrder: () => ({ mutateAsync: vi.fn(), isPending: false }),
    useDeleteSalesOrder: () => ({ mutateAsync: vi.fn(), isPending: false }),
    useResetSalesOrderPlanning: () => ({ mutateAsync: vi.fn(), isPending: false }),
    useCreateDoFromSalesOrder: () => ({ mutateAsync: vi.fn(), isPending: false }),
  };
});

const api = vi.hoisted(() => ({ apiFetch: vi.fn() }));
vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  apiFetch: (...a: unknown[]) => api.apiFetch(...a),
}));

import SalesOrdersGrid from './SalesOrdersGrid';

const PLACEHOLDER = 'Search SO, customer, product or agent...';

const ROW = {
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
};

function answerList() {
  api.apiFetch.mockImplementation(async () => ({
    ok: true,
    status: 200,
    json: async () => ({
      data: [ROW],
      pagination: { total: 80, page: 1, limit: 25 },
      empty: false,
    }),
    text: async () => '',
  }));
}

/** Every list GET the grid sent, as parsed search params. */
function listRequests(): URLSearchParams[] {
  return api.apiFetch.mock.calls
    .map((c) => String(c[0]))
    .filter((url) => url.includes('sales-orders?'))
    .map((url) => new URLSearchParams(url.slice(url.indexOf('?') + 1)));
}

function lastListRequest(): URLSearchParams {
  const all = listRequests();
  expect(all.length).toBeGreaterThan(0);
  return all.at(-1)!;
}

function renderGrid() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SalesOrdersGrid />
    </QueryClientProvider>,
  );
}

function searchBox() {
  return screen.getByRole('textbox', { name: PLACEHOLDER });
}

let replaceState: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  nav.search = '';
  prefs.getUserListColumnConfig.mockResolvedValue({ listing_key: '/scm/sales-orders', config: null });
  prefs.upsertUserListColumnConfig.mockImplementation(async (k: string, p: unknown) => ({
    listing_key: k,
    config: p,
  }));
  answerList();
  replaceState = vi.spyOn(window.history, 'replaceState');
});

afterEach(() => {
  replaceState.mockRestore();
});

describe('SalesOrdersGrid search chips', () => {
  it('S1: every chip plus the typed text reaches the list GET as its own query param', async () => {
    const user = userEvent.setup();
    renderGrid();
    expect(await screen.findByText('SO900001')).toBeInTheDocument();

    await user.type(searchBox(), 'SO371334{Enter}');
    await user.type(searchBox(), 'Acme Trading{Enter}');
    expect(screen.getByRole('button', { name: 'Remove SO371334' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Remove Acme Trading' })).toBeInTheDocument();
    // Typed, not Entered: searched live (F5) beside the chips.
    await user.type(searchBox(), 'Fakeco');

    await waitFor(() => {
      const queries = lastListRequest().getAll('query');
      expect(queries).toHaveLength(3);
      expect(queries).toEqual(expect.arrayContaining(['SO371334', 'Acme Trading', 'Fakeco']));
    });
  });

  it('S1: chips alone (no typed text) send exactly one query per chip', async () => {
    const user = userEvent.setup();
    renderGrid();
    await screen.findByText('SO900001');

    await user.type(searchBox(), 'SO1{Enter}SO2{Enter}');
    await waitFor(() => {
      expect(lastListRequest().getAll('query')).toEqual(['SO1', 'SO2']);
    });
  });

  it('S2: a list URL with two query params (Back from a record) restores two chips and searches both', async () => {
    nav.search = 'page=1&limit=25&sort=order_date&dir=desc&query=SO371334&query=Acme%2C+Trading';
    renderGrid();

    expect(await screen.findByRole('button', { name: 'Remove SO371334' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Remove Acme, Trading' })).toBeInTheDocument();
    await waitFor(() => {
      expect(lastListRequest().getAll('query')).toEqual(['SO371334', 'Acme, Trading']);
    });
    // Restored as chips, not as one run of typed text.
    expect(searchBox()).toHaveValue('');
  });

  it('S3: adding a chip returns to page 1 and keeps the sort', async () => {
    nav.search = 'page=3&limit=25&sort=order_date&dir=desc&query=SO1';
    const user = userEvent.setup();
    renderGrid();
    await screen.findByText('SO900001');
    await waitFor(() => expect(lastListRequest().get('page')).toBe('3'));

    await user.type(searchBox(), 'SO2{Enter}');
    await waitFor(() => {
      const req = lastListRequest();
      expect(req.getAll('query')).toEqual(['SO1', 'SO2']);
      expect(req.get('page')).toBe('1');
      expect(req.get('sort')).toBe('order_date');
      expect(req.get('dir')).toBe('desc');
    });
  });

  it('S3: removing a chip returns to page 1', async () => {
    nav.search = 'page=3&limit=25&query=SO1&query=SO2';
    const user = userEvent.setup();
    renderGrid();
    await user.click(await screen.findByRole('button', { name: 'Remove SO1' }));
    await waitFor(() => {
      const req = lastListRequest();
      expect(req.getAll('query')).toEqual(['SO2']);
      expect(req.get('page')).toBe('1');
    });
  });

  it('S4: adding chips writes them into the address bar via history.replaceState', async () => {
    const user = userEvent.setup();
    renderGrid();
    await screen.findByText('SO900001');

    await user.type(searchBox(), 'SO1{Enter}SO2{Enter}');
    await waitFor(() => {
      const urls = replaceState.mock.calls.map((c) => String(c[2] ?? ''));
      const written = urls
        .map((u) => new URL(u, 'http://localhost/scm/sales-orders'))
        .filter((u) => u.searchParams.getAll('query').length === 2);
      expect(written.length).toBeGreaterThan(0);
      const last = written.at(-1)!;
      expect(last.searchParams.getAll('query')).toEqual(['SO1', 'SO2']);
      expect(last.searchParams.get('page')).toBe('1');
      expect(last.pathname).toBe('/scm/sales-orders');
    });
  });
});

describe('SalesOrdersGrid search chips inside a sales agent record', () => {
  it('S4 guard: pinned to an agent, adding a chip searches but never rewrites the address bar', async () => {
    const user = userEvent.setup();
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <SalesOrdersGrid salesAgentId="AG1" />
      </QueryClientProvider>,
    );
    await screen.findByText('SO900001');

    await user.type(searchBox(), 'SO1{Enter}SO2{Enter}');
    // The search still runs, pinned to the agent ...
    await waitFor(() => {
      const req = lastListRequest();
      expect(req.getAll('query')).toEqual(['SO1', 'SO2']);
      expect(req.get('sales_agent_id')).toBe('AG1');
    });
    // ... but the record's own URL is left alone: that address bar belongs to the agent record.
    expect(replaceState).not.toHaveBeenCalled();
  });
});

describe('SalesOrdersGrid search chips: emptied text settles at once', () => {
  /** The list GETs sent after the first `skip` ones, as their `query` values. */
  const queriesFrom = (skip: number) => listRequests().slice(skip).map((r) => r.getAll('query'));

  it('Clear with typed text present sends one request with no query, and none with the old text', async () => {
    nav.search = 'page=1&limit=25&query=SO1';
    const user = userEvent.setup();
    renderGrid();
    await screen.findByRole('button', { name: 'Remove SO1' });

    await user.type(searchBox(), 'Fakeco');
    await waitFor(() => expect(lastListRequest().getAll('query')).toEqual(['SO1', 'Fakeco']));
    const before = listRequests().length;

    await user.click(screen.getByRole('button', { name: 'Clear search' }));
    await waitFor(() => expect(lastListRequest().getAll('query')).toEqual([]));
    // Past the debounce: a stale word would have gone out by now.
    await new Promise((r) => setTimeout(r, 400));
    const after = queriesFrom(before);
    expect(after.length).toBeGreaterThan(0);
    expect(after.filter((q) => q.includes('Fakeco'))).toEqual([]);
    expect(after.at(-1)).toEqual([]);
  });

  it('Enter commits the chip without a request carrying the stale typed text', async () => {
    const user = userEvent.setup();
    renderGrid();
    await screen.findByText('SO900001');

    await user.type(searchBox(), 'Fak');
    await waitFor(() => expect(lastListRequest().getAll('query')).toEqual(['Fak']));
    const before = listRequests().length;

    await user.type(searchBox(), 'eco{Enter}');
    await waitFor(() => expect(lastListRequest().getAll('query')).toEqual(['Fakeco']));
    await new Promise((r) => setTimeout(r, 400));
    const after = queriesFrom(before);
    expect(after.filter((q) => q.includes('Fak'))).toEqual([]);
    expect(after.every((q) => q.length === 1 && q[0] === 'Fakeco')).toBe(true);
  });
});
