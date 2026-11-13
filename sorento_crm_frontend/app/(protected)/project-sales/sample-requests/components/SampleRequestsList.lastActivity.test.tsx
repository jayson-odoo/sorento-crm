/**
 * FORMS-LAST-ACTIVITY F1/F2: the Sample requests list shows a "Last activity" column (one line,
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
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => '/project-sales/sample-requests',
  useSearchParams: () => new URLSearchParams(url.search),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));
vi.mock('@/lib/listing-column-preferences/listColumnPreferencesService', () => ({
  getUserListColumnConfig: vi.fn(async (listingKey: string) => ({ listing_key: listingKey, config: null })),
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
const useSampleRequestsQuery = vi.hoisted(() => vi.fn());
vi.mock('../hooks/useSampleRequests', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../hooks/useSampleRequests')>();
  return { ...actual, useSampleRequestsQuery: (...args: unknown[]) => useSampleRequestsQuery(...args) };
});
import List from './SampleRequestsList';
import { formatDateTimeInMalaysia } from '@/lib/helpers';

// A plain naive ISO string, like the API returns; the expectation goes through the same helper.
const STAMP = '2026-03-10T09:05:00';
const STAMP_TEXT = formatDateTimeInMalaysia(STAMP);
const ROW = { id: 'sr-1', request_no: 'ZZT-SR-0001', status: 'submitted', status_label: 'Submitted', customer_name: 'ZZT Buyer', created_at: '2026-01-01T00:00:00', last_activity_at: STAMP };

beforeEach(() => {
  url.search = '';
  vi.clearAllMocks();
  useSampleRequestsQuery.mockReset();
  useSampleRequestsQuery.mockReturnValue({
    data: { data: [ROW], pagination: { total: 1, page: 1, limit: 25 } },
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

describe('Sample requests list - Last activity', () => {
  it('has a "Last activity" column header', async () => {
    renderList();
    await screen.findByText('ZZT-SR-0001');
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
    await screen.findByText('ZZT-SR-0001');
    await waitFor(() => expect(useSampleRequestsQuery).toHaveBeenCalled());
    const first = useSampleRequestsQuery.mock.calls[0][0] as { sorting?: Array<{ id: string; desc: boolean }> };
    expect(first.sorting).toEqual([{ id: 'last_activity_at', desc: true }]);
  });
});
