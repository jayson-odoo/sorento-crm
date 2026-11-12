/**
 * SEARCH-CHIPS slice 2 (UAC S1, S2, S4 as for Sales orders): the Order inquiries Documents list's
 * search box in chips mode. Plan `documentation/plans/ui/PLAN-search-chips-b-12nov.md`.
 *
 * The REAL `useOrderInquiryHeaders` -> `listOrderInquiryHeaders` -> `buildDataGridParams` chain
 * runs and only `apiFetch` is stubbed, so the assertions read the actual
 * GET /api/v1/project-sales/order-inquiry-headers the browser would send.
 * Red first: the list passes no chips to `ListSearchInput` and sends one `query`.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver =
  ResizeObserverStub;
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}
Element.prototype.scrollIntoView = vi.fn();

const nav = vi.hoisted(() => ({ search: '', replace: vi.fn() }));
vi.mock('next/navigation', () => ({
  usePathname: () => '/project-sales/order-inquiries',
  useRouter: () => ({ push: vi.fn(), replace: nav.replace }),
  useSearchParams: () => new URLSearchParams(nav.search),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({
    resetToDefaults: async () => {},
    isLoading: false,
  }),
}));
vi.mock('@/services/userSelectService', () => ({
  getUserLookup: vi.fn(async () => [{ id: 'zzt-u1', name: 'ZZT User One' }]),
}));
vi.mock('@/hooks/usePermissions', () => ({ useHasPermission: () => false }));
vi.mock(
  '../../_shared/services/orderInquiryReserveService',
  async (importOriginal) => {
    const actual =
      await importOriginal<
        typeof import('../../_shared/services/orderInquiryReserveService')
      >();
    return {
      ...actual,
      getReserveStatusSummary: async () => ({
        parked: 0,
        needs_reserve: 0,
        notice_parked: 0,
        reserved: 0,
        my_parked_requests: 0,
        my_parked_notices: 0,
      }),
    };
  },
);
// The REAL `listOrderInquiryHeaders`; only the facet summary is stubbed.
vi.mock(
  '../../_shared/services/orderInquiryService',
  async (importOriginal) => {
    const actual =
      await importOriginal<
        typeof import('../../_shared/services/orderInquiryService')
      >();
    return {
      ...actual,
      getOrderInquiryWorklistSummary: vi.fn(async () => ({
        agents: [],
        projects: [],
      })),
    };
  },
);

const api = vi.hoisted(() => ({ apiFetch: vi.fn() }));
vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  apiFetch: (...a: unknown[]) => api.apiFetch(...a),
}));

import { OrderInquiryHeadersList } from './OrderInquiryHeadersList';

const PLACEHOLDER = 'Search OI, SO, customer, project or product...';

const ROW = {
  id: 'oi-1',
  inquiry_no: 'OI-ZZT-0001',
  raised_at: '2026-07-01T00:00:00',
  raised_by_name: 'ZZT User One',
  so_number: 'ZZTSO0001',
  customer_name: 'ZZT Fakeco Customer',
  lines_total: 1,
  lines_to_confirm: 1,
  qty_total: '5',
  status: 'outstanding',
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

/** Every Documents list GET the page sent, as parsed search params. */
function listRequests(): URLSearchParams[] {
  return api.apiFetch.mock.calls
    .map((c) => String(c[0]))
    .filter((u) => u.includes('/order-inquiry-headers?'))
    .map((u) => new URLSearchParams(u.slice(u.indexOf('?') + 1)));
}

function lastListRequest(): URLSearchParams {
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
    (u) => new URL(u, 'http://localhost/project-sales/order-inquiries'),
  );
}

function renderList() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <OrderInquiryHeadersList />
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

describe('OrderInquiryHeadersList search chips', () => {
  it('two chips plus the typed text reach GET /order-inquiry-headers as one query param each', async () => {
    const user = userEvent.setup();
    renderList();
    expect(await screen.findByText('OI-ZZT-0001')).toBeInTheDocument();

    await user.type(searchBox(), 'OI2611001{Enter}');
    await user.type(searchBox(), 'Acme Trading{Enter}');
    expect(
      screen.getByRole('button', { name: 'Remove OI2611001' }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Remove Acme Trading' }),
    ).toBeInTheDocument();
    await user.type(searchBox(), 'Fakeco');

    await waitFor(() => {
      const queries = lastListRequest().getAll('query');
      expect(queries).toHaveLength(3);
      expect(queries).toEqual(
        expect.arrayContaining(['OI2611001', 'Acme Trading', 'Fakeco']),
      );
    });
  });

  it('a list URL with two query params restores two chips and searches both', async () => {
    nav.search = 'state=all&query=OI2611001&query=Acme%2C+Trading';
    renderList();

    expect(
      await screen.findByRole('button', { name: 'Remove OI2611001' }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Remove Acme, Trading' }),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(lastListRequest().getAll('query')).toEqual([
        'OI2611001',
        'Acme, Trading',
      ]);
    });
    expect(searchBox()).toHaveValue('');
  });

  it('adding chips writes them into the address bar', async () => {
    const user = userEvent.setup();
    renderList();
    await screen.findByText('OI-ZZT-0001');

    await user.type(searchBox(), 'OI1{Enter}OI2{Enter}');
    await waitFor(() => {
      const written = writtenUrls().filter(
        (u) => u.searchParams.getAll('query').length === 2,
      );
      expect(written.length).toBeGreaterThan(0);
      const last = written.at(-1)!;
      expect(last.searchParams.getAll('query')).toEqual(['OI1', 'OI2']);
      expect(last.pathname).toBe('/project-sales/order-inquiries');
    });
  });
});
