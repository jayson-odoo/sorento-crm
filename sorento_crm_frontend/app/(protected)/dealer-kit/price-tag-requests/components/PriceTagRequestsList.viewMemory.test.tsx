/**
 * LIST-FILTER-MEMORY-4: the Price Tag Requests list remembers its sort and status filter per
 * user, the same way Stock Inquiries and Sales Orders do. The REAL
 * `useListingViewPreferences` runs; only its transport and the list service are stubbed.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('next/navigation', () => ({
  usePathname: () => '/dealer-kit/price-tag-requests',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
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
const listPriceTagRequests = vi.hoisted(() => vi.fn());
vi.mock('../../services/priceTagRequestService', () => ({
  listPriceTagRequests: (...a: unknown[]) => listPriceTagRequests(...a),
  claimPriceTagRequest: vi.fn(),
}));

import PriceTagRequestsList from './PriceTagRequestsList';

const LISTING_KEY = '/dealer-kit/price-tag-requests';
type Call = { sort?: string; dir?: string; status?: string };

const ROW = {
  id: 'req-1', doc_number: 'PT-000001', debtor_code: null, debtor_name: 'ZZT Dealer', needed_by_date: null,
  notes: null, status: 'designing', line_count: 1, created_at: '2026-09-01T00:00:00Z',
  assigned_to_id: null, assigned_to_name: null, contact_name: 'ZZT Sales',
};

function stored(config: Record<string, unknown> | null) {
  service.getUserListColumnConfig.mockResolvedValue({ listing_key: LISTING_KEY, config });
  service.upsertUserListColumnConfig.mockImplementation(async (key: string, payload: unknown) => ({
    listing_key: key,
    config: payload,
  }));
}
const calls = () => listPriceTagRequests.mock.calls.map((c) => c[0] as Call);

beforeEach(() => {
  if (!window.matchMedia) {
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: false, media: query, onchange: null, addListener: vi.fn(), removeListener: vi.fn(),
      addEventListener: vi.fn(), removeEventListener: vi.fn(), dispatchEvent: vi.fn(),
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
  vi.clearAllMocks();
  listPriceTagRequests.mockResolvedValue({ data: [ROW], pagination: { total: 1, page: 1, limit: 50 } });
});
afterEach(() => cleanup());

function renderIt(client = new QueryClient({ defaultOptions: { queries: { retry: false } } })) {
  render(
    <QueryClientProvider client={client}>
      <PriceTagRequestsList />
    </QueryClientProvider>,
  );
  return client;
}

describe('Price Tag Requests list remembers sort and filters', () => {
  it('waits for the stored view, then every request carries its sort and status (coming back, reload)', async () => {
    stored({
      version: 1,
      sorting: [{ id: 'doc_number', desc: false }],
      filters: { status: 'designing,approved' },
      filtersVersion: 1,
    });
    renderIt();

    await screen.findByText('PT-000001');
    expect(calls().length).toBeGreaterThan(0);
    for (const c of calls()) {
      expect(c.sort).toBe('doc_number');
      expect(c.dir).toBe('asc');
      expect(c.status).toBe('designing,approved');
    }
  });

  it('a sort change is written for this listing and comes back on the next visit', async () => {
    stored(null);
    const client = renderIt();
    await screen.findByText('PT-000001');

    fireEvent.click(screen.getByText('Doc Number'));
    await waitFor(() => expect(service.upsertUserListColumnConfig).toHaveBeenCalled(), { timeout: 3000 });
    const [key, payload] = service.upsertUserListColumnConfig.mock.calls.at(-1)!;
    expect(key).toBe(LISTING_KEY);
    expect(payload.sorting).toEqual([{ id: 'doc_number', desc: false }]);

    cleanup();
    listPriceTagRequests.mockClear();
    renderIt(client);
    await screen.findByText('PT-000001');
    expect(calls()[0].sort).toBe('doc_number');
  });

  it('Clear drops the remembered filter, refetches unfiltered and stores null', async () => {
    stored({
      version: 1,
      sorting: [{ id: 'created_at', desc: true }],
      filters: { status: 'designing' },
      filtersVersion: 1,
    });
    renderIt();
    fireEvent.click(await screen.findByRole('button', { name: /^Clear filter:/ }));

    await waitFor(() => expect(calls().at(-1)!.status).toBeUndefined());
    await waitFor(() => expect(service.upsertUserListColumnConfig).toHaveBeenCalled(), { timeout: 3000 });
    const [key, payload] = service.upsertUserListColumnConfig.mock.calls.at(-1)!;
    expect(key).toBe(LISTING_KEY);
    expect(payload).toMatchObject({ filters: null, filtersVersion: null });
  });

  it('nothing stored: the shipped default, no filter', async () => {
    stored(null);
    renderIt();
    await screen.findByText('PT-000001');
    const last = calls().at(-1)!;
    expect(last.sort).toBe('created_at');
    expect(last.dir).toBe('desc');
    expect(last.status).toBeUndefined();
  });
});
