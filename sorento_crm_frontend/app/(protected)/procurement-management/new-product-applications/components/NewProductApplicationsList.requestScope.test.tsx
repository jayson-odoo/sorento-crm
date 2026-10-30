/**
 * PORTAL-P4-REQUESTS S5: the New Product Application list for a LIMITED user (`.view_own` + `.create`) and for staff
 * alike: every column header sorts (P4-23), and a limited user with `.create` gets New.
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
  usePathname: () => '/procurement-management/new-product-applications',
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
const useListQuery = vi.hoisted(() => vi.fn());
vi.mock('../hooks/useNewProductApplications', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../hooks/useNewProductApplications')>();
  return { ...actual, useNewProductApplicationsQuery: (...args: unknown[]) => useListQuery(...args) };
});

import NewProductApplicationsList from './NewProductApplicationsList';

const LIMITED = ['procurement.new_product_applications.view_own', 'procurement.new_product_applications.create'];
const STAFF = ['procurement.new_product_applications.view', 'procurement.new_product_applications.create'];
// The grid's own titles, Number to Date (NewProductApplicationsList.tsx columns).
const COLUMNS = ['Number', 'Status', 'Inquiry', 'Customer', 'First line', 'Lines', 'Done', 'Needed by', 'Date'];

beforeEach(() => {
  cleanup();
  useListQuery.mockReturnValue({
    data: {
      data: [
        {
          id: 'npa-1', application_no: 'NPA-000001', status: 'submitted', status_label: 'Submitted', source: 'portal',
          applicant_id: 'u-1', applicant_name: 'Owner', stock_inquiry_id: null, stock_inquiry_number: 'SI26-0412',
          customer_name: 'Acme', project_name: null, first_line: 'Sink', lines_total: 2, lines_done: 0, opened_codes: [],
          needed_by: null, submitted_at: null, created_at: '2026-10-10T01:00:00',
        },
      ],
      pagination: { page: 1, limit: 25, total: 1 },
    },
    isLoading: false, isPlaceholderData: false, refetch: vi.fn(), isFetching: false, error: null,
  });
});

function mount(slugs: string[]) {
  held = new Set(slugs);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <NewProductApplicationsList />
    </QueryClientProvider>,
  );
}

describe('every New Product Application column header sorts, for limited and staff alike', () => {
  it.each([['limited', LIMITED], ['staff', STAFF]])('%s: each header is a sort button', async (_n, slugs) => {
    mount(slugs);
    await screen.findByText('NPA-000001');
    const missing: string[] = [];
    for (const title of COLUMNS) {
      const th = screen.queryAllByText(title).map((el) => el.closest('th')).find(Boolean);
      const sortable = !!th?.querySelector('svg.lucide-chevrons-up-down, svg.lucide-arrow-up, svg.lucide-arrow-down');
      if (!sortable) missing.push(title);
    }
    expect(missing).toEqual([]);
  });
});

describe('New for a limited user', () => {
  it('a limited user with create gets Create (L4: was New)', async () => {
    mount(LIMITED);
    await screen.findByText('NPA-000001');
    expect(screen.getByRole('button', { name: /^create$/i })).toBeTruthy();
  });
});

describe('Create label (L4, owner a25895124 Q3 a)', () => {
  it('staff: the primary action reads exactly "Create", never "New"', async () => {
    mount(STAFF);
    await screen.findByText('NPA-000001');
    expect(screen.getAllByRole('button', { name: 'Create' }).length).toBeGreaterThan(0);
    expect(screen.queryByRole('button', { name: /^new$/i })).toBeNull();
  });
});
