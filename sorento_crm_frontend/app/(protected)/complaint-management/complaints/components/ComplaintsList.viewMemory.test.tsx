/**
 * LIST-FILTER-MEMORY-4: the Complaints list remembers its sort and filters per user, the
 * same way Stock Inquiries and Sales Orders do (PLAN-listing-view-memory,
 * PLAN-list-filter-memory-4). The REAL `useListingViewPreferences` runs; only the
 * preferences transport and the data hook are stubbed.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/complaint-management/complaints',
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
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
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));
vi.mock('@/components/my-downloads/EntityDownloadsButton', () => ({
  EntityDownloadsButton: () => <span>downloads</span>,
}));
const useComplaints = vi.hoisted(() => vi.fn());
vi.mock('../hooks/useComplaints', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../hooks/useComplaints')>();
  return {
    ...actual,
    useComplaints: (...a: unknown[]) => useComplaints(...a),
    useExportComplaintPdf: () => ({ mutate: vi.fn(), isPending: false }),
  };
});
vi.mock('../../complaint-root-causes/hooks/useComplaintRootCauses', () => ({
  useComplaintRootCausesSelect: () => ({ data: [{ id: 'rc-1', name: 'ZZT Cause One' }], error: null, refetch: vi.fn() }),
}));
vi.mock('../../complaint-resolutions/hooks/useComplaintResolutions', () => ({
  useComplaintResolutionsSelect: () => ({ data: [{ id: 'rs-1', name: 'ZZT Fix One' }], error: null, refetch: vi.fn() }),
}));
vi.mock('@/services/userSelectService', () => ({
  getUserLookup: vi.fn(async () => [
    { id: 'u-ann', respond_user_id: 'resp-ann', name: 'ZZT Ann', email: 'a@example.test' },
  ]),
}));

import ComplaintsList from './ComplaintsList';

const LISTING_KEY = '/complaint-management/complaints';
type Params = Record<string, unknown> & { enabled?: boolean; sorting: unknown };

function stored(config: Record<string, unknown> | null) {
  service.getUserListColumnConfig.mockResolvedValue({ listing_key: LISTING_KEY, config });
  service.upsertUserListColumnConfig.mockImplementation(async (key: string, payload: unknown) => ({
    listing_key: key,
    config: payload,
  }));
}

const asList = (v: unknown): string[] =>
  v == null || v === '' ? [] : Array.isArray(v) ? (v as string[]) : String(v).split(',');
/** Only fetches that actually went out: a held query (`enabled: false`) fetches nothing. */
const fetched = () =>
  useComplaints.mock.calls.map((c) => c[0] as Params).filter((p) => p.enabled !== false);

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
  useComplaints.mockReturnValue({
    data: {
      data: [{ id: 'c-1', complaint_number: 'CP-26-0001', status: 'new', created_at: '2026-07-01T00:00:00' }],
      pagination: { total: 1, page: 1, limit: 50 },
    },
    isLoading: false, isPlaceholderData: false, isFetching: false, error: null, refetch: vi.fn(),
  });
});
afterEach(() => cleanup());

function renderIt(client = new QueryClient({ defaultOptions: { queries: { retry: false } } })) {
  render(
    <QueryClientProvider client={client}>
      <ComplaintsList />
    </QueryClientProvider>,
  );
  return client;
}

describe('Complaints list remembers sort and filters', () => {
  it('holds the query, then every fetch carries the stored sort and filters (coming back, reload)', async () => {
    stored({
      version: 1,
      sorting: [{ id: 'complaint_number', desc: false }],
      filters: { status: 'new,approved', assigned_to: 'resp-ann', root_cause_ids: ['rc-1'] },
      filtersVersion: 1,
    });
    renderIt();

    expect((useComplaints.mock.calls[0][0] as Params).enabled).toBe(false);
    await waitFor(() => expect(fetched().length).toBeGreaterThan(0));
    for (const p of fetched()) {
      expect(p.sorting).toEqual([{ id: 'complaint_number', desc: false }]);
      expect(asList(p.status)).toEqual(['new', 'approved']);
      expect(asList(p.assigned_to)).toEqual(['resp-ann']);
      expect(asList(p.root_cause_ids)).toEqual(['rc-1']);
    }
    expect(service.getUserListColumnConfig).toHaveBeenCalledWith(LISTING_KEY);
  });

  it('a sort change is written for this listing and comes back on the next visit', async () => {
    stored(null);
    const client = renderIt();
    await waitFor(() => expect(fetched().length).toBeGreaterThan(0));

    fireEvent.click(await screen.findByText('Complaint Number'));
    await waitFor(() => expect(service.upsertUserListColumnConfig).toHaveBeenCalled(), { timeout: 3000 });
    const [key, payload] = service.upsertUserListColumnConfig.mock.calls.at(-1)!;
    expect(key).toBe(LISTING_KEY);
    expect(payload.sorting).not.toEqual([{ id: 'created_at', desc: true }]);
    expect(payload).not.toHaveProperty('searchQuery');

    // Leave the list and come back within the session: the same cache answers.
    cleanup();
    useComplaints.mockClear();
    renderIt(client);
    await waitFor(() => expect(fetched().length).toBeGreaterThan(0));
    expect(fetched()[0].sorting).toEqual(payload.sorting);
  });

  it('Clear drops the remembered filters, refetches unfiltered and stores null', async () => {
    stored({
      version: 1,
      sorting: [{ id: 'created_at', desc: true }],
      filters: { status: 'new' },
      filtersVersion: 1,
    });
    renderIt();
    const clear = await screen.findByRole('button', { name: /^Clear filter:/ });
    fireEvent.click(clear);

    await waitFor(() => expect(asList(fetched().at(-1)!.status)).toEqual([]));
    await waitFor(() => expect(service.upsertUserListColumnConfig).toHaveBeenCalled(), { timeout: 3000 });
    const [key, payload] = service.upsertUserListColumnConfig.mock.calls.at(-1)!;
    expect(key).toBe(LISTING_KEY);
    expect(payload).toMatchObject({ filters: null, filtersVersion: null });
  });

  it('nothing stored: the shipped default, no filter, nothing written', async () => {
    stored(null);
    renderIt();
    await waitFor(() => expect(fetched().length).toBeGreaterThan(0));
    const last = fetched().at(-1)!;
    expect(last.sorting).toEqual([{ id: 'last_activity_at', desc: true }]);
    expect(asList(last.status)).toEqual([]);
    await new Promise((r) => setTimeout(r, 1000));
    expect(service.upsertUserListColumnConfig).not.toHaveBeenCalled();
  });
});
