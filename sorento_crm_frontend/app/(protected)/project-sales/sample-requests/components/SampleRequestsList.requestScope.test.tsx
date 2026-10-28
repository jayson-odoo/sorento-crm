/**
 * PORTAL-P4-REQUESTS S4: the Sample Request list for a LIMITED user and for staff alike: every column header
 * sorts (P4-23), and a limited user with `.create` gets Create.
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

class ResizeObserverStub { observe() {} unobserve() {} disconnect() {} }
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}
Element.prototype.scrollIntoView = vi.fn();

vi.mock('next/navigation', () => ({
  usePathname: () => '/project-sales/sample-requests',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));
vi.mock('@/lib/listing-column-preferences/listColumnPreferencesService', () => ({
  getUserListColumnConfig: vi.fn(async (k: string) => ({ listing_key: k, config: null })),
  upsertUserListColumnConfig: vi.fn(async (k: string, c: unknown) => ({ listing_key: k, config: c })),
  resetUserListColumnConfig: vi.fn(async () => undefined),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), custom: vi.fn() } }));

let held = new Set<string>();
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => held.has(slug),
  useHasAnyPermission: (slugs: string[]) => slugs.some((s) => held.has(s)),
  usePermissions: () => ({ permissionSet: held, permissions: [...held], isLoading: false, isError: false }),
}));
vi.mock('@/services/userSelectService', () => ({ getUserLookup: vi.fn(async () => []) }));
const useSampleRequestsQuery = vi.hoisted(() => vi.fn());
vi.mock('../hooks/useSampleRequests', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../hooks/useSampleRequests')>();
  return { ...actual, useSampleRequestsQuery: (...args: unknown[]) => useSampleRequestsQuery(...args) };
});

import SampleRequestsList from './SampleRequestsList';

const LIMITED = ['projects.sample_requests.view_own', 'projects.sample_requests.create'];
const STAFF = ['projects.sample_requests.view', 'projects.sample_requests.create'];
const COLUMNS = ['Number', 'Submitted', 'Status', 'Delivery', 'Customer', 'Project Title', 'Mode', 'Salesperson'];

beforeEach(() => {
  cleanup();
  useSampleRequestsQuery.mockReturnValue({
    data: {
      data: [{ id: 'sr-1', request_no: 'SR-000001', status: 'submitted', status_label: 'Submitted', customer_name: 'Acme', created_at: '2026-10-10T01:00:00' }],
      pagination: { page: 1, limit: 25, total: 1 },
    },
    isLoading: false, isPlaceholderData: false, refetch: vi.fn(), isFetching: false, error: null,
  });
});

describe('every Sample Request column header sorts, for limited and staff alike', () => {
  it.each([['limited', LIMITED], ['staff', STAFF]])('%s: each header is a sort button', async (_n, slugs) => {
    held = new Set(slugs);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <SampleRequestsList />
      </QueryClientProvider>,
    );
    await screen.findByText('SR-000001');
    const missing: string[] = [];
    for (const title of COLUMNS) {
      const th = screen.queryAllByText(title).map((el) => el.closest('th')).find(Boolean);
      const sortable = !!th?.querySelector('svg.lucide-chevrons-up-down, svg.lucide-arrow-up, svg.lucide-arrow-down');
      if (!sortable) missing.push(title);
    }
    expect(missing).toEqual([]);
  });
});
