/**
 * FORMS-LAST-ACTIVITY browser-pass fix: the Stock inquiries Last activity header sorts. Fake data only.
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

// A plain naive ISO string, like the API returns; the expectation goes through the same helper.
const STAMP = '2026-03-10T09:05:00';
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

describe('Stock inquiries list - Last activity header sorts', () => {
  it('cycling the header (desc, off, asc) reaches the data hook as last_activity_at ascending', async () => {
    const user = userEvent.setup();
    renderList();
    await screen.findByText(/SI-26-0184/);
    const header = () => screen.getAllByText('Last activity')[0].closest('button') as HTMLElement;
    await user.click(header());
    await user.click(header());
    await waitFor(() => {
      const params = useStockInquiries.mock.calls.at(-1)?.[0] as { sorting?: Array<{ id: string; desc: boolean }> };
      expect(params.sorting).toEqual([{ id: 'last_activity_at', desc: false }]);
    });
  });
});
