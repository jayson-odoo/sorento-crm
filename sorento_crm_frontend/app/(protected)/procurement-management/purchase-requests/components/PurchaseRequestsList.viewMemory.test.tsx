/**
 * LIST-FILTER-MEMORY-4: the Purchase Requests and Sponsorship Forms lists (one component, two
 * routes) remember their sort and filters per user, the same way Stock Inquiries and Sales
 * Orders do. Each route is its own listing key, so the two lists never share a remembered view.
 * The REAL `useListingViewPreferences` runs; only its transport and the data hook are stubbed.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
Element.prototype.scrollIntoView = vi.fn();

const nav = vi.hoisted(() => ({ pathname: '/procurement-management/purchase-requests' }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => nav.pathname,
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
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => false,
  usePermissions: () => ({ permissions: [], permissionSet: new Set(), isLoading: false }),
}));
vi.mock('@/services/userSelectService', () => ({
  getUserLookup: vi.fn().mockResolvedValue([{ id: 'u-1', name: 'ZZT Alice' }]),
}));
vi.mock('@/components/common/LookupBoundLabel', () => ({
  default: ({ value }: { value: string }) => <span>{value}</span>,
}));
const usePR = vi.hoisted(() => vi.fn());
vi.mock('../hooks/usePurchaseRequests', () => ({
  useBulkDeletePurchaseRequests: () => ({ mutateAsync: vi.fn(), isPending: false }),
  usePurchaseRequests: (params: unknown) => usePR(params),
}));

import PurchaseRequestsList from './PurchaseRequestsList';

const PR_KEY = '/procurement-management/purchase-requests';
const SF_KEY = '/procurement-management/sponsorship-forms';
type RequestType = 'purchase_request' | 'sponsorship_form';
type Params = Record<string, unknown> & { enabled?: boolean; sorting: unknown };

const ROW = {
  id: 'pr-1', request_number: 'ZZT-PR-001', request_type: 'purchase_request', approval_status: 'pending', status: 'draft',
  customer_name: 'ZZT Customer', purpose: 'ZZT purpose', requested_by: 'ZZT', submitted_at: '2026-01-01T00:00:00',
  created_at: '2026-01-01T00:00:00', revision_no: 0, assigned_to_name: null, handled_by_name: null,
};

function stored(config: Record<string, unknown> | null) {
  service.getUserListColumnConfig.mockImplementation(async (key: string) => ({ listing_key: key, config }));
  service.upsertUserListColumnConfig.mockImplementation(async (key: string, payload: unknown) => ({
    listing_key: key,
    config: payload,
  }));
}
const setOf = (v: unknown): string[] =>
  (Array.isArray(v) ? v.map(String) : String(v ?? '').split(',')).map((s) => s.trim()).filter(Boolean).sort();
const fetched = () => usePR.mock.calls.map((c) => c[0] as Params).filter((p) => p.enabled !== false);

function renderIt(
  requestType: RequestType,
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } }),
) {
  nav.pathname = requestType === 'sponsorship_form' ? SF_KEY : PR_KEY;
  render(
    <QueryClientProvider client={client}>
      <PurchaseRequestsList requestType={requestType} basePath={nav.pathname} />
    </QueryClientProvider>,
  );
  return client;
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  usePR.mockReturnValue({
    data: { data: [ROW], pagination: { total: 1, page: 1, limit: 50 } },
    isLoading: false, isPlaceholderData: false, isFetching: false, error: null, refetch: vi.fn(),
  });
});
afterEach(() => cleanup());

describe.each([
  ['Purchase Requests', 'purchase_request' as RequestType, PR_KEY],
  ['Sponsorship Forms', 'sponsorship_form' as RequestType, SF_KEY],
])('%s list remembers sort and filters', (_label, requestType, key) => {
  it('holds the query, then every fetch carries the stored sort and filters (coming back, reload)', async () => {
    stored({
      version: 1,
      sorting: [{ id: 'request_number', desc: false }],
      filters: { approval_status: 'pending,approved', assigned_to: 'u-1' },
      filtersVersion: 1,
    });
    renderIt(requestType);

    expect((usePR.mock.calls[0][0] as Params).enabled).toBe(false);
    await waitFor(() => expect(fetched().length).toBeGreaterThan(0));
    for (const p of fetched()) {
      expect(p.sorting).toEqual([{ id: 'request_number', desc: false }]);
      expect(setOf(p.approvalStatus)).toEqual(['approved', 'pending']);
      expect(setOf(p.assignedTo)).toEqual(['u-1']);
      // The page's own type is never overridden by a remembered blob.
      expect(p.requestType).toBe(requestType);
    }
    expect(service.getUserListColumnConfig).toHaveBeenCalledWith(key);
  });

  it('a sort change is written for this listing and comes back on the next visit', async () => {
    stored(null);
    const client = renderIt(requestType);
    await screen.findByText('ZZT-PR-001');
    await waitFor(() => expect(fetched().length).toBeGreaterThan(0));

    fireEvent.click(screen.getByText('Customer'));
    await waitFor(() => expect(service.upsertUserListColumnConfig).toHaveBeenCalled(), { timeout: 3000 });
    const [writtenKey, payload] = service.upsertUserListColumnConfig.mock.calls.at(-1)!;
    expect(writtenKey).toBe(key);
    expect(payload.sorting).not.toEqual([{ id: 'created_at', desc: true }]);

    cleanup();
    usePR.mockClear();
    renderIt(requestType, client);
    await waitFor(() => expect(fetched().length).toBeGreaterThan(0));
    expect(fetched()[0].sorting).toEqual(payload.sorting);
  });

  it('Clear drops the remembered filters, refetches unfiltered and stores null', async () => {
    stored({
      version: 1,
      sorting: [{ id: 'created_at', desc: true }],
      filters: { approval_status: 'pending' },
      filtersVersion: 1,
    });
    renderIt(requestType);
    fireEvent.click(await screen.findByRole('button', { name: /^Clear filter:/ }));

    await waitFor(() => expect(setOf(fetched().at(-1)!.approvalStatus)).toEqual([]));
    await waitFor(() => expect(service.upsertUserListColumnConfig).toHaveBeenCalled(), { timeout: 3000 });
    const [writtenKey, payload] = service.upsertUserListColumnConfig.mock.calls.at(-1)!;
    expect(writtenKey).toBe(key);
    expect(payload).toMatchObject({ filters: null, filtersVersion: null });
  });
});
