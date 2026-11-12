/**
 * SEARCH-CHIPS slice 2 (UAC S1, S2, S4 as for Sales orders): the Delivery orders list's search
 * box in chips mode. Plan `documentation/plans/ui/PLAN-search-chips-b-12nov.md`.
 *
 * The REAL `useOrders` -> `fetchOrdersPage` chain runs and only `apiFetch` is stubbed, so the
 * assertions read the actual request. `fetchOrdersPage` has two transports: the plain list
 * (GET /api/v1/order-management/orders, `query`) and, with an advanced filter, POST
 * /api/v1/list-query/search, whose `quick_search` becomes a LIST of strings. The first three
 * tests read the search values off whichever one the list sent; the fourth pins the list-query
 * body.
 * Red first: the list passes no chips to `ListSearchInput` and sends one value.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

if (!window.matchMedia) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })) as unknown as typeof window.matchMedia;
}
if (!('ResizeObserver' in window)) {
  (window as unknown as { ResizeObserver: unknown }).ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}
Element.prototype.scrollIntoView = vi.fn();

const nav = vi.hoisted(() => ({ search: '', replace: vi.fn() }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: nav.replace }),
  useSearchParams: () => new URLSearchParams(nav.search),
  usePathname: () => '/order-management/orders',
}));
vi.mock(
  '@/lib/listing-column-preferences/listColumnPreferencesService',
  () => ({
    getUserListColumnConfig: vi.fn(async (listingKey: string) => ({
      listing_key: listingKey,
      config: null,
    })),
    upsertUserListColumnConfig: vi.fn(
      async (listingKey: string, config: unknown) => ({
        listing_key: listingKey,
        config,
      }),
    ),
    resetUserListColumnConfig: vi.fn(async () => undefined),
  }),
);
vi.mock('../../shared/hooks/use-order-status-select-query', () => ({
  useOrderStatusSelectQuery: () => ({
    data: [{ id: 'st-new', status_name: 'ZZT New' }],
  }),
}));
vi.mock('../actions', () => ({ OrderRowActions: () => null }));
vi.mock('@/components/upload-activity', () => ({
  useImportJobDrawer: () => ({ notifyImportQueued: vi.fn() }),
}));
vi.mock('@/hooks/useDeferredBulkAction', () => ({
  useDeferredBulkAction: () => ({ start: vi.fn(), pending: false }),
}));
vi.mock('@/lib/pending-entity-store', () => ({
  pendingEntityKey: (t: string, id: string) => `${t}:${id}`,
  usePendingEntityKeys: () => new Set<string>(),
}));
vi.mock(
  '@/app/(protected)/system-management/import-jobs/autocount-pull/hooks/useAutocountPull',
  () => ({
    useAutocountPullAction: () => ({
      label: 'Pull from AutoCount',
      onClick: vi.fn(),
      disabled: false,
    }),
  }),
);
vi.mock(
  '@/app/(protected)/system-management/import-jobs/autocount-pull/components/PullScopeDialog',
  () => ({ PullScopeDialog: () => null }),
);
vi.mock('@/components/template/TemplateUploadDialog', () => ({
  TemplateUploadDialog: () => null,
}));
vi.mock('./OrderTrackingUploadDialog', () => ({
  OrderTrackingUploadDialog: () => null,
}));
vi.mock('./OrderLinesImportDialog', () => ({
  OrderLinesImportDialog: () => null,
}));

const api = vi.hoisted(() => ({ apiFetch: vi.fn() }));
vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  apiFetch: (...a: unknown[]) => api.apiFetch(...a),
}));

import OrdersList from './OrdersList';

const PLACEHOLDER = 'Search delivery orders...';
const LIST_GET = '/api/v1/order-management/orders?';
const LIST_SEARCH = '/api/v1/list-query/search';

const LIST_BODY = {
  data: [{ id: 'o-1', order_number: 'ZZT-DO-1' }],
  pagination: { total: 80, page: 1, limit: 50, pages: 2 },
  empty: false,
};

function answerList() {
  api.apiFetch.mockImplementation(async (url: unknown) => {
    const u = String(url);
    const body =
      u.includes(LIST_GET) || u.includes(LIST_SEARCH) ? LIST_BODY : [];
    return {
      ok: true,
      status: 200,
      json: async () => body,
      text: async () => JSON.stringify(body),
    };
  });
}

type Sent = {
  transport: 'get' | 'search';
  values: string[];
  body?: Record<string, unknown>;
};

/** Every list request the page sent, with the search values it carried. */
function listRequests(): Sent[] {
  const out: Sent[] = [];
  for (const [url, init] of api.apiFetch.mock.calls as [
    unknown,
    RequestInit | undefined,
  ][]) {
    const u = String(url);
    if (u.includes(LIST_GET)) {
      out.push({
        transport: 'get',
        values: new URLSearchParams(u.slice(u.indexOf('?') + 1)).getAll(
          'query',
        ),
      });
    } else if (u.includes(LIST_SEARCH)) {
      const body = JSON.parse(String(init?.body ?? '{}')) as Record<
        string,
        unknown
      >;
      const q = body.quick_search;
      const values = Array.isArray(q)
        ? q.map(String)
        : typeof q === 'string' && q
          ? [q]
          : [];
      out.push({ transport: 'search', values, body });
    }
  }
  return out;
}

function lastListRequest(): Sent {
  const all = listRequests();
  expect(all.length).toBeGreaterThan(0);
  return all.at(-1)!;
}

/** Every URL the list wrote into the address bar, however it wrote it. */
function writtenUrls(): URL[] {
  const viaHistory = (replaceState.mock.calls as unknown[][]).map((c) =>
    String(c[2] ?? ''),
  );
  const viaRouter = nav.replace.mock.calls.map((c) => String(c[0] ?? ''));
  return [...viaHistory, ...viaRouter].map(
    (u) => new URL(u, 'http://localhost/order-management/orders'),
  );
}

function renderList() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <OrdersList />
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

describe('OrdersList search chips', () => {
  it('two chips plus the typed text reach the list request as one value each', async () => {
    const user = userEvent.setup();
    renderList();
    expect(await screen.findByText('ZZT-DO-1')).toBeInTheDocument();

    await user.type(searchBox(), 'DO2611001{Enter}');
    await user.type(searchBox(), 'Acme Trading{Enter}');
    expect(
      screen.getByRole('button', { name: 'Remove DO2611001' }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Remove Acme Trading' }),
    ).toBeInTheDocument();
    await user.type(searchBox(), 'Fakeco');

    await waitFor(() => {
      const { values } = lastListRequest();
      expect(values).toHaveLength(3);
      expect(values).toEqual(
        expect.arrayContaining(['DO2611001', 'Acme Trading', 'Fakeco']),
      );
    });
  });

  it('a list URL with two query params restores two chips and searches both', async () => {
    nav.search = 'page=1&limit=50&query=DO2611001&query=Acme%2C+Trading';
    renderList();

    expect(
      await screen.findByRole('button', { name: 'Remove DO2611001' }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Remove Acme, Trading' }),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(lastListRequest().values).toEqual(['DO2611001', 'Acme, Trading']);
    });
    expect(searchBox()).toHaveValue('');
  });

  it('adding chips writes them into the address bar', async () => {
    const user = userEvent.setup();
    renderList();
    await screen.findByText('ZZT-DO-1');

    await user.type(searchBox(), 'DO1{Enter}DO2{Enter}');
    await waitFor(() => {
      const written = writtenUrls().filter(
        (u) => u.searchParams.getAll('query').length === 2,
      );
      expect(written.length).toBeGreaterThan(0);
      const last = written.at(-1)!;
      expect(last.searchParams.getAll('query')).toEqual(['DO1', 'DO2']);
      expect(last.pathname).toBe('/order-management/orders');
    });
  });

  it('with an advanced filter, POST /list-query/search carries quick_search as a list of every chip', async () => {
    const adv = { op: 'and', children: [] };
    const sp = new URLSearchParams();
    sp.set('page', '1');
    sp.set('limit', '50');
    sp.append('query', 'DO2611001');
    sp.append('query', 'Acme, Trading');
    sp.set('advFilter', encodeURIComponent(JSON.stringify(adv)));
    nav.search = sp.toString();
    renderList();

    await waitFor(() => {
      const last = lastListRequest();
      expect(last.transport).toBe('search');
      expect(last.body?.quick_search).toEqual(['DO2611001', 'Acme, Trading']);
    });
  });
});
