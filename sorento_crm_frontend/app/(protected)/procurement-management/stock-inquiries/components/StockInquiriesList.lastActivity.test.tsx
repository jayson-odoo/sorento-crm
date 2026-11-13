/**
 * FORMS-LAST-ACTIVITY F1/F2/U11 (replaces the old coalesce/Revised test): the Stock inquiries list shows a "Last activity" column (one line,
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
  usePathname: () => '/procurement-management/stock-inquiries',
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
vi.mock('@/components/my-downloads/EntityDownloadsButton', () => ({
  EntityDownloadsButton: () => <span>downloads</span>,
}));
const useStockInquiries = vi.hoisted(() => vi.fn());
vi.mock('../hooks/useStockInquiries', () => ({
  useStockInquiries: (...a: unknown[]) => useStockInquiries(...a),
  useBulkDeleteStockInquiries: () => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false }),
}));
import List from './StockInquiriesList';
import { formatDateTimeInMalaysia } from '@/lib/helpers';

// A plain naive ISO string, like the API returns; the expectation goes through the same helper.
const STAMP = '2026-03-10T09:05:00';
const STAMP_TEXT = formatDateTimeInMalaysia(STAMP);
const ROW = { id: 'si-1', inquiry_number: 'SI-26-0184', product_code: 'ABC-1', status: 'pending_purchasing', revision_no: 2, created_at: '2026-03-01T00:00:00', updated_at: '2026-03-02T00:00:00', last_revised_at: '2026-03-05T00:00:00', last_activity_at: STAMP };

beforeEach(() => {
  url.search = '';
  vi.clearAllMocks();
  useStockInquiries.mockReset();
  useStockInquiries.mockReturnValue({
    data: { data: [ROW], empty: false, pagination: { total: 1, page: 1, limit: 50 } },
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

describe('Stock inquiries list - Last activity', () => {
  it('has a "Last activity" column header', async () => {
    renderList();
    await screen.findByText(/SI-26-0184/);
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
    await screen.findByText(/SI-26-0184/);
    await waitFor(() => expect(useStockInquiries).toHaveBeenCalled());
    const first = useStockInquiries.mock.calls[0][0] as { sorting?: Array<{ id: string; desc: boolean }> };
    expect(first.sorting).toEqual([{ id: 'last_activity_at', desc: true }]);
  });

  it('shows the stored stamp, not the last revision date, even for a revised row', async () => {
    renderList();
    await screen.findByText(STAMP_TEXT);
    expect(screen.queryByText(formatDateTimeInMalaysia('2026-03-05T00:00:00'))).toBeNull();
  });
});
