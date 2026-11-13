/**
 * FORMS-LAST-ACTIVITY F1/F2: the Complaints list shows a "Last activity" column (one line,
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
  usePathname: () => '/complaint-management/complaints',
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
  useComplaintRootCausesSelect: () => ({ data: [], error: null, refetch: vi.fn() }),
}));
vi.mock('../../complaint-resolutions/hooks/useComplaintResolutions', () => ({
  useComplaintResolutionsSelect: () => ({ data: [], error: null, refetch: vi.fn() }),
}));
import List from './ComplaintsList';
import { formatDateTimeInMalaysia } from '@/lib/helpers';

// A plain naive ISO string, like the API returns; the expectation goes through the same helper.
const STAMP = '2026-03-10T09:05:00';
const STAMP_TEXT = formatDateTimeInMalaysia(STAMP);
const ROW = { id: 'c-1', complaint_number: 'ZZT-C-001', customer_name: 'ZZT Customer', status: 'new', complaint_date: '2026-01-05', created_at: '2026-01-05T00:00:00', last_activity_at: STAMP };

beforeEach(() => {
  url.search = '';
  vi.clearAllMocks();
  useComplaints.mockReset();
  useComplaints.mockReturnValue({
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

describe('Complaints list - Last activity', () => {
  it('has a "Last activity" column header', async () => {
    renderList();
    await screen.findByText('ZZT-C-001');
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
    await screen.findByText('ZZT-C-001');
    await waitFor(() => expect(useComplaints).toHaveBeenCalled());
    const first = useComplaints.mock.calls[0][0] as { sorting?: Array<{ id: string; desc: boolean }> };
    expect(first.sorting).toEqual([{ id: 'last_activity_at', desc: true }]);
  });
});
