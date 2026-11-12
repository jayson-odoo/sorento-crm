/**
 * FORMS-LAST-ACTIVITY F1/F2/F3: the Purchase requests list shows a "Last activity" column (one line,
 * formatDateTimeInMalaysia, no "Revised" prefix) and sorts by it, newest first, by default.
 * Red test: written before the column exists. Fake data only.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor } from '@testing-library/react';
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
Element.prototype.hasPointerCapture = vi.fn();

const url = vi.hoisted(() => ({ search: '' }));
const remembered = vi.hoisted(() => ({ config: null as Record<string, unknown> | null }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => '/procurement-management/purchase-requests',
  useSearchParams: () => new URLSearchParams(url.search),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));
vi.mock('@/lib/listing-column-preferences/listColumnPreferencesService', () => ({
  getUserListColumnConfig: vi.fn(async (listingKey: string) => ({ listing_key: listingKey, config: remembered.config })),
  upsertUserListColumnConfig: vi.fn(async (listingKey: string, config: unknown) => ({ listing_key: listingKey, config })),
  resetUserListColumnConfig: vi.fn(async () => undefined),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), custom: vi.fn() } }));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => true,
  usePermissions: () => ({ permissions: [], permissionSet: new Set(), isLoading: false }),
}));
vi.mock('@/services/userSelectService', () => ({
  getUserLookup: vi.fn(async () => []),
}));
vi.mock('@/components/my-downloads/EntityDownloadsButton', () => ({
  EntityDownloadsButton: () => <span>downloads</span>,
}));
vi.mock('@/components/common/LookupBoundLabel', () => ({
  default: ({ value }: { value: string }) => <span>{value}</span>,
}));
const usePR = vi.hoisted(() => vi.fn());
vi.mock('../hooks/usePurchaseRequests', () => ({
  useBulkDeletePurchaseRequests: () => ({ mutateAsync: vi.fn(), isPending: false }),
  usePurchaseRequests: (params: unknown) => usePR(params),
}));
import List from './PurchaseRequestsList';
import { formatDateTimeInMalaysia } from '@/lib/helpers';

// A plain naive ISO string, like the API returns; the expectation goes through the same helper.
const STAMP = '2026-03-10T09:05:00';
const STAMP_TEXT = formatDateTimeInMalaysia(STAMP);
const ROW = { id: 'pr-1', request_number: 'ZZT-PR-001', request_type: 'purchase_request', approval_status: 'pending', status: 'draft', customer_name: 'ZZT Customer', purpose: 'ZZT purpose', requested_by: 'ZZT', submitted_at: '2026-01-01T00:00:00', created_at: '2026-01-01T00:00:00', revision_no: 0, assigned_to_name: null, handled_by_name: null, last_activity_at: STAMP };

beforeEach(() => {
  url.search = '';
  remembered.config = null;
  vi.clearAllMocks();
  usePR.mockReset();
  usePR.mockReturnValue({
    data: { data: [ROW], pagination: { total: 1, page: 1, limit: 50 } },
    isLoading: false, isPlaceholderData: false, isFetching: false, isError: false, error: null, refetch: vi.fn(),
  });
});
afterEach(() => cleanup());

function renderList() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return render(
    <QueryClientProvider client={client}>
      <List />
    </QueryClientProvider>,
  );
}

describe('Purchase requests list - Last activity', () => {
  it('has a "Last activity" column header', async () => {
    renderList();
    await screen.findByText('ZZT-PR-001');
    expect(screen.getAllByText('Last activity').length).toBeGreaterThan(0);
  });

  it('renders the stamp as dd/mm/yyyy, h:mm am/pm with no "Revised" prefix', async () => {
    renderList();
    expect(await screen.findByText(STAMP_TEXT)).toBeInTheDocument();
    expect(STAMP_TEXT).toMatch(/^\d{2}\/\d{2}\/\d{4}, \d{1,2}:\d{2} (am|pm)$/i);
    expect(screen.queryByText(/Revised/)).toBeNull();
  });

  it('first request sorts by last_activity_at, newest first', async () => {
    renderList();
    await screen.findByText('ZZT-PR-001');
    await waitFor(() => expect(usePR).toHaveBeenCalled());
    const first = usePR.mock.calls[0][0] as { sorting?: Array<{ id: string; desc: boolean }> };
    expect(first.sorting).toEqual([{ id: 'last_activity_at', desc: true }]);
  });

  it('F3: a last-activity range in the remembered view reaches the data hook as from/to', async () => {
    remembered.config = {
      version: 1,
      sorting: [{ id: 'last_activity_at', desc: true }],
      filters: { last_activity_from: '2026-03-11', last_activity_to: '2026-03-12' },
      filtersVersion: 1,
    };
    renderList();
    await screen.findByText('ZZT-PR-001');
    await waitFor(() => {
      const params = usePR.mock.calls.at(-1)?.[0] as Record<string, unknown>;
      const entries = Object.entries(params).map(([k, v]) => [k.replace(/[_-]/g, '').toLowerCase(), String(v)]);
      const from = entries.find(([k]) => k === 'lastactivityfrom');
      const to = entries.find(([k]) => k === 'lastactivityto');
      expect(from?.[1]).toBe('2026-03-11');
      expect(to?.[1]).toBe('2026-03-12');
    });
  });
});
