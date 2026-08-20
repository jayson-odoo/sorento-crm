/**
 * Stock inquiry list - remembered view (PLAN-listing-view-memory).
 *
 * The whole listing renders with the REAL `useListingViewPreferences`; only the
 * preferences transport and the data hook are stubbed. This pins the pieces the unit
 * tests cannot see together:
 *   - the data query is held until the stored view resolves and then fires ONCE,
 *     already sorted and filtered (AC-B3);
 *   - a restored filter is stated as a chip above the grid and its Clear drops the
 *     filter, refetches unfiltered and writes an explicit null (AC-C1 / AC-C2);
 *   - a blob from an older `filtersVersion` is discarded while the sort is kept (AC-B4);
 *   - page number and search text are never in the write (AC-D1 / AC-D2).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  render,
  screen,
  cleanup,
  fireEvent,
  waitFor,
} from '@testing-library/react';
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

vi.mock('next/navigation', () => ({
  usePathname: () => '/procurement-management/stock-inquiries',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({
    resetToDefaults: async () => {},
    isLoading: false,
  }),
}));

const service = vi.hoisted(() => ({
  getUserListColumnConfig: vi.fn(),
  upsertUserListColumnConfig: vi.fn(),
}));
vi.mock(
  '@/lib/listing-column-preferences/listColumnPreferencesService',
  () => ({
    getUserListColumnConfig: (...a: unknown[]) =>
      service.getUserListColumnConfig(...a),
    upsertUserListColumnConfig: (...a: unknown[]) =>
      service.upsertUserListColumnConfig(...a),
    resetUserListColumnConfig: vi.fn(async () => undefined),
  }),
);

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), custom: vi.fn() },
}));

vi.mock('@/components/my-downloads/EntityDownloadsButton', () => ({
  EntityDownloadsButton: () => <span>downloads</span>,
}));

const hooks = vi.hoisted(() => ({ useStockInquiries: vi.fn() }));
vi.mock('../hooks/useStockInquiries', () => ({
  useStockInquiries: (...a: unknown[]) => hooks.useStockInquiries(...a),
  useBulkDeleteStockInquiries: () => ({
    mutate: vi.fn(),
    mutateAsync: vi.fn(),
    isPending: false,
  }),
}));

import StockInquiriesList from './StockInquiriesList';
import type { StockInquiry } from '../types/stockInquiry.types';

const LISTING_KEY = '/procurement-management/stock-inquiries';

type ListParams = {
  pageIndex: number;
  pageSize: number;
  sorting: { id: string; desc: boolean }[];
  searchQuery: string;
  statuses: string[];
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

function inquiry(over: Partial<StockInquiry> = {}): StockInquiry {
  return {
    id: 'si-1',
    inquiry_number: 'SI-26-0184',
    product_code: 'ABC-1',
    status: 'pending_purchasing',
    revision_no: 0,
    created_at: new Date('2026-07-01T00:00:00'),
    updated_at: new Date('2026-07-01T00:00:00'),
    ...over,
  } as StockInquiry;
}

function mockList(rows: StockInquiry[]) {
  hooks.useStockInquiries.mockReturnValue({
    data: {
      data: rows,
      empty: rows.length === 0,
      pagination: { page: 1, total: rows.length },
    },
    isLoading: false,
    isFetching: false,
    refetch: vi.fn(),
  });
}

function renderList() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <StockInquiriesList />
    </QueryClientProvider>,
  );
}

/** Every set of params the data hook was asked to fetch with (`enabled: true`). */
function enabledFetches(): ListParams[] {
  return hooks.useStockInquiries.mock.calls
    .map((c) => c[0] as ListParams)
    .filter((p) => p.enabled);
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('StockInquiriesList remembered view', () => {
  it('holds the data query, then fetches once with the stored sort and filter applied (AC-B1 / AC-B3)', async () => {
    storedConfig({
      version: 1,
      sorting: [{ id: 'status', desc: false }],
      filters: { statuses: ['pending_purchasing'] },
      filtersVersion: 1,
    });
    mockList([inquiry()]);
    renderList();

    // The first render is gated: nothing has been fetched yet.
    expect(
      (hooks.useStockInquiries.mock.calls[0][0] as ListParams).enabled,
    ).toBe(false);

    expect(await screen.findByText('SI-26-0184')).toBeInTheDocument();

    const fetched = enabledFetches();
    expect(fetched.length).toBeGreaterThan(0);
    // No fetch ever went out with the shipped defaults - every enabled call already
    // carries the remembered view.
    for (const p of fetched) {
      expect(p.sorting).toEqual([{ id: 'status', desc: false }]);
      expect(p.statuses).toEqual(['pending_purchasing']);
    }
  });

  it('states the restored filter as a chip and Clear drops it, refetches and writes null (AC-C1 / AC-C2)', async () => {
    storedConfig({
      version: 1,
      sorting: [{ id: 'created_at', desc: true }],
      filters: { statuses: ['pending_purchasing'] },
      filtersVersion: 1,
    });
    mockList([inquiry()]);
    renderList();

    const clear = await screen.findByRole('button', {
      name: 'Clear filter: Pending purchasing',
    });
    // The chip label is the human status name, not the raw code.
    expect(clear.closest('span')?.textContent).toContain('Pending purchasing');

    fireEvent.click(clear);

    await waitFor(() => {
      expect(
        screen.queryByRole('button', { name: /^Clear filter:/ }),
      ).not.toBeInTheDocument();
    });
    const last = enabledFetches().at(-1)!;
    expect(last.statuses).toEqual([]);
    expect(last.pageIndex).toBe(0);

    // The clear reaches storage as an explicit null, debounced.
    await waitFor(
      () => {
        expect(service.upsertUserListColumnConfig).toHaveBeenCalled();
      },
      { timeout: 3000 },
    );
    const [key, payload] =
      service.upsertUserListColumnConfig.mock.calls.at(-1)!;
    expect(key).toBe(LISTING_KEY);
    expect(payload).toMatchObject({ filters: null, filtersVersion: null });
    expect(payload.sorting).toEqual([{ id: 'created_at', desc: true }]);
    // Never remembered: page number and search text (AC-D1 / AC-D2).
    expect(payload).not.toHaveProperty('pageIndex');
    expect(payload).not.toHaveProperty('page');
    expect(payload).not.toHaveProperty('searchQuery');
    expect(payload).not.toHaveProperty('search');
  });

  it('discards a filter blob written by an older page shape but keeps the sort (AC-B4)', async () => {
    storedConfig({
      version: 1,
      sorting: [{ id: 'status', desc: false }],
      // An older shape of this page stored a bare string under a different key.
      filters: { status: 'pending_purchasing' },
      filtersVersion: 0,
    });
    mockList([inquiry()]);
    renderList();

    expect(await screen.findByText('SI-26-0184')).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: /^Clear filter:/ }),
    ).not.toBeInTheDocument();

    const last = enabledFetches().at(-1)!;
    expect(last.statuses).toEqual([]);
    expect(last.sorting).toEqual([{ id: 'status', desc: false }]);
    // Applying the stored view is not a change, so nothing is written back and the
    // stale blob is left in the row for the next real filter change to overwrite.
    await new Promise((r) => setTimeout(r, 1000));
    expect(service.upsertUserListColumnConfig).not.toHaveBeenCalled();
  });

  it('falls back to the shipped default (newest first, no filter) with nothing stored (AC-B2)', async () => {
    storedConfig(null);
    mockList([inquiry()]);
    renderList();

    expect(await screen.findByText('SI-26-0184')).toBeInTheDocument();
    const last = enabledFetches().at(-1)!;
    expect(last.sorting).toEqual([{ id: 'created_at', desc: true }]);
    expect(last.statuses).toEqual([]);
    expect(
      screen.queryByRole('button', { name: /^Clear filter:/ }),
    ).not.toBeInTheDocument();
  });
});
