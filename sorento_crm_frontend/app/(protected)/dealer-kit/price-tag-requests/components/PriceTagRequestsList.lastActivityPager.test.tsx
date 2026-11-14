/**
 * FORMS-LAST-ACTIVITY review fix: the Price tag requests list carries its Last activity range into the record
 * link, so the detail page's prev/next walks the same filtered page. Fake data only.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor, fireEvent } from '@testing-library/react';
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
const push = vi.hoisted(() => vi.fn());
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => '/dealer-kit/price-tag-requests',
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
const listPriceTagRequests = vi.hoisted(() => vi.fn());
vi.mock('../../services/priceTagRequestService', () => ({
  listPriceTagRequests: (...a: unknown[]) => listPriceTagRequests(...a),
  claimPriceTagRequest: vi.fn(),
}));
import List from './PriceTagRequestsList';

// A plain naive ISO string, like the API returns; the expectation goes through the same helper.
const STAMP = '2026-03-10T09:05:00';
const ROW_BASE = { id: 'req-1', doc_number: 'PT-000001', debtor_code: null, debtor_name: 'ZZT Dealer', needed_by_date: null, notes: null, status: 'designing', line_count: 1, created_at: '2026-01-01T00:00:00Z', assigned_to_id: 'user-1', assigned_to_name: 'ZZT Mei', contact_name: 'ZZT Sam', last_activity_at: STAMP };


beforeEach(() => {
  url.search = '';
  vi.clearAllMocks();
  listPriceTagRequests.mockReset();
  listPriceTagRequests.mockResolvedValue({ data: [{ ...ROW_BASE }], pagination: { total: 1, page: 1, limit: 50 } });
});
afterEach(() => cleanup());

describe('Price tag requests list - Last activity range in the record link', () => {
  it('the row link carries last_activity_from and last_activity_to', async () => {
    const user = userEvent.setup();
    const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
    render(
      <QueryClientProvider client={client}>
        <List />
      </QueryClientProvider>,
    );
    await user.click(await screen.findByRole('button', { name: /^filters/i }));
    const input = await screen.findByLabelText('Last activity');
    fireEvent.change(input, { target: { value: '11/03/2026 - 12/03/2026' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    await waitFor(() => expect(listPriceTagRequests.mock.calls.at(-1)?.[0]).toMatchObject({ last_activity_from: '2026-03-11' }));
    await user.keyboard('{Escape}');
    await user.click(await screen.findByText('PT-000001'));
    const href = String(push.mock.calls.at(-1)?.[0] ?? '');
    expect(href).toContain('/dealer-kit/price-tag-requests/req-1');
    expect(href).toContain('last_activity_from=2026-03-11');
    expect(href).toContain('last_activity_to=2026-03-12');
  });
});
