/**
 * SEARCH-CHIPS slice 2 (UAC S1, S2, S4 as for Sales orders): the Consignments list's search box
 * in chips mode. The backend is slice 1's (`GET /api/v1/scm/sales-orders`, `doc_type=consignment`),
 * so this is frontend only. Plan `documentation/plans/ui/PLAN-search-chips-b-12nov.md`.
 *
 * The REAL `useSalesOrders` -> `getSalesOrders` -> `buildDataGridParams` chain runs and only
 * `apiFetch` is stubbed, so the assertions read the actual list GET the browser would send.
 * Red first: the list passes no chips to `ListSearchInput` and sends one `query`.
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

vi.mock('@/lib/toast', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
    warning: vi.fn(),
    custom: vi.fn(),
  },
}));

const nav = vi.hoisted(() => ({ search: '', replace: vi.fn() }));
vi.mock('next/navigation', async (importOriginal) => ({
  ...(await importOriginal<typeof import('next/navigation')>()),
  useRouter: () => ({ push: vi.fn(), replace: nav.replace }),
  usePathname: () => '/scm/consignments',
  useSearchParams: () => new URLSearchParams(nav.search),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({
    resetToDefaults: async () => {},
    isLoading: false,
  }),
}));
vi.mock(
  '@/lib/listing-column-preferences/listColumnPreferencesService',
  () => ({
    getUserListColumnConfig: vi.fn(async () => ({
      listing_key: '/scm/consignments',
      config: null,
    })),
    upsertUserListColumnConfig: vi.fn(
      async (listingKey: string, payload: unknown) => ({
        listing_key: listingKey,
        config: payload,
      }),
    ),
    resetUserListColumnConfig: vi.fn(async () => undefined),
  }),
);

vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => true,
  usePermissions: () => ({
    permissions: [],
    permissionSet: new Set(),
    isLoading: false,
  }),
}));

const EMPTY = { data: [], isLoading: false };
vi.mock('../../hooks/useScmOptions', () => ({
  useCustomerOptions: () => EMPTY,
  useOrderTypeOptions: () => EMPTY,
  useProductOptions: () => EMPTY,
  useSupplierOptions: () => EMPTY,
  useCategoryOptions: () => EMPTY,
  useWarehouseOptions: () => EMPTY,
}));

// The real list hook (and through it the real service + `buildDataGridParams`); the rest stubbed.
vi.mock('../../hooks/useSalesOrders', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('../../hooks/useSalesOrders')>();
  return {
    ...actual,
    useResetSalesOrderPlanning: () => ({
      mutateAsync: vi.fn(),
      isPending: false,
    }),
  };
});

const api = vi.hoisted(() => ({ apiFetch: vi.fn() }));
vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  apiFetch: (...a: unknown[]) => api.apiFetch(...a),
}));

import { ConsignmentsList } from './ConsignmentsList';

const PLACEHOLDER = 'Search number, customer or product...';

const ROW = {
  id: 'cg-1',
  so_number: 'ZZT-CG-0001',
  doc_type: 'consignment',
  customer_name: 'ZZT CONSIGN CUSTOMER A',
  status: 'open',
  order_date: '2026-06-10',
  lines: [],
  created_at: '2026-06-10T00:00:00',
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

/** Every consignment list GET the page sent, as parsed search params. */
function listRequests(): URLSearchParams[] {
  return api.apiFetch.mock.calls
    .map((c) => String(c[0]))
    .filter((u) => u.includes('sales-orders?'))
    .map((u) => new URLSearchParams(u.slice(u.indexOf('?') + 1)))
    .filter((p) => p.get('doc_type') === 'consignment');
}

function lastListRequest(): URLSearchParams {
  const all = listRequests();
  expect(all.length).toBeGreaterThan(0);
  return all.at(-1)!;
}

function writtenUrls(): URL[] {
  const viaHistory = (replaceState.mock.calls as unknown[][]).map((c) =>
    String(c[2] ?? ''),
  );
  const viaRouter = nav.replace.mock.calls.map((c) => String(c[0] ?? ''));
  return [...viaHistory, ...viaRouter].map(
    (u) => new URL(u, 'http://localhost/scm/consignments'),
  );
}

function renderList() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <ConsignmentsList />
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
  answerList();
  replaceState = vi.spyOn(window.history, 'replaceState');
});

afterEach(() => {
  replaceState.mockRestore();
});

describe('ConsignmentsList search chips', () => {
  it('two chips plus the typed text reach GET /scm/sales-orders?doc_type=consignment as one query each', async () => {
    const user = userEvent.setup();
    renderList();
    expect(await screen.findByText('ZZT-CG-0001')).toBeInTheDocument();

    await user.type(searchBox(), 'CN371334{Enter}');
    await user.type(searchBox(), 'Acme Trading{Enter}');
    expect(
      screen.getByRole('button', { name: 'Remove CN371334' }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Remove Acme Trading' }),
    ).toBeInTheDocument();
    await user.type(searchBox(), 'Fakeco');

    await waitFor(() => {
      const queries = lastListRequest().getAll('query');
      expect(queries).toHaveLength(3);
      expect(queries).toEqual(
        expect.arrayContaining(['CN371334', 'Acme Trading', 'Fakeco']),
      );
    });
  });

  it('a list URL with two query params restores two chips and searches both', async () => {
    nav.search = 'page=1&limit=25&query=CN371334&query=Acme%2C+Trading';
    renderList();

    expect(
      await screen.findByRole('button', { name: 'Remove CN371334' }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Remove Acme, Trading' }),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(lastListRequest().getAll('query')).toEqual([
        'CN371334',
        'Acme, Trading',
      ]);
    });
    expect(searchBox()).toHaveValue('');
  });

  it('adding chips writes them into the address bar', async () => {
    const user = userEvent.setup();
    renderList();
    await screen.findByText('ZZT-CG-0001');

    await user.type(searchBox(), 'CN1{Enter}CN2{Enter}');
    await waitFor(() => {
      const written = writtenUrls().filter(
        (u) => u.searchParams.getAll('query').length === 2,
      );
      expect(written.length).toBeGreaterThan(0);
      const last = written.at(-1)!;
      expect(last.searchParams.getAll('query')).toEqual(['CN1', 'CN2']);
      expect(last.pathname).toBe('/scm/consignments');
    });
  });
});
