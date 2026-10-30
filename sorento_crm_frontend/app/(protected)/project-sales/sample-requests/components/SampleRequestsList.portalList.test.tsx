/**
 * PORTAL-P4-REQUESTS L2 (hand test 3, owner a25895124 Q1 a / Q3 a): a salesperson limited to their own
 * sample requests (`.view_own`, not `.view`) gets the PORTAL's own list body inside the CRM page: cards with a
 * card / list toggle, the portal's filter fields, long press -> preview, "Create" on the filter row, no
 * portal chrome, rows from `/api/v1/my-requests/submissions/sample_request` (its own list call). Staff keep the DataGrid.
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  expectCreateOnFilterRow,
  expectNoPortalChrome,
  expectPortalFilterFields,
  expectViewToggle,
  jsonResponse,
  urlsOf,
} from '@/components/common/portalListContract.testkit';

class ResizeObserverStub { observe() {} unobserve() {} disconnect() {} }
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}
Element.prototype.scrollIntoView = vi.fn();

const apiFetch = vi.hoisted(() => vi.fn());
vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return { ...actual, apiFetch: (...a: unknown[]) => apiFetch(...a) };
});
vi.mock('next/navigation', () => ({
  usePathname: () => '/project-sales/sample-requests',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
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
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), custom: vi.fn() } }));
vi.mock('@/services/userSelectService', () => ({ getUserLookup: vi.fn(async () => []) }));
vi.mock('@/components/my-downloads/EntityDownloadsButton', () => ({ EntityDownloadsButton: () => <span>downloads</span> }));

let held = new Set<string>();
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => held.has(slug),
  useHasAnyPermission: (slugs: string[]) => slugs.some((s) => held.has(s)),
  usePermissions: () => ({ permissionSet: held, permissions: [...held], isLoading: false, isError: false }),
}));
// The STAFF list's rows (a number the portal rows below never use).
vi.mock('../hooks/useSampleRequests', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../hooks/useSampleRequests')>();
  return {
    ...actual,
    useSampleRequestsQuery: () => ({
      data: { data: [{ id: 'staff-1', request_no: 'STAFF-0001', status: 'submitted', status_label: 'Submitted', customer_name: 'Acme', created_at: '2026-10-10T01:00:00' }], pagination: { page: 1, limit: 25, total: 1 } },
      isLoading: false, isPlaceholderData: false, refetch: vi.fn(), isFetching: false, error: null,
    }),
  };
});

import SampleRequestsList from './SampleRequestsList';

const LIMITED = ['projects.sample_requests.view_own', 'projects.sample_requests.create'];
const STAFF = ['projects.sample_requests.view', 'projects.sample_requests.create', 'projects.sample_requests.process'];

const PORTAL_ROW = {
  id: 'mine-1', request_no: 'MYR-0001', status: 'submitted', status_label: 'Submitted', customer_name: 'Buyer One',
  request_date: '2026-08-20T02:00:00',
};

function mount(slugs: string[]) {
  held = new Set(slugs);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SampleRequestsList />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  cleanup();
  window.localStorage.clear();
  apiFetch.mockReset();
  apiFetch.mockImplementation(async (url: unknown) => {
    const u = String(url);
    if (u.includes('/api/v1/my-requests/submissions/sample_request')) return jsonResponse({ data: [PORTAL_ROW], pagination: { total: 1, page: 1, limit: 50 } });
    return jsonResponse({ items: [], data: [], pagination: { total: 0, page: 1, limit: 50 } });
  });
});

describe('Sample Request list, limited user: the portal list body', () => {
  it('reads its rows from my-requests, never the portal route', async () => {
    mount(LIMITED);
    expect(await screen.findByText('MYR-0001')).toBeInTheDocument();
    const urls = urlsOf(apiFetch);
    expect(urls.some((u) => u.includes('/api/v1/my-requests/submissions/sample_request'))).toBe(true);
    expect(urls.some((u) => u.includes('/public/portal'))).toBe(false);
  });

  it('shows cards, not the staff DataGrid', async () => {
    mount(LIMITED);
    await screen.findByText('MYR-0001');
    expect(screen.queryByRole('table')).toBeNull();
    expect(screen.queryByText('STAFF-0001')).toBeNull();
  });

  it('has the card / list toggle', async () => {
    mount(LIMITED);
    await screen.findByText('MYR-0001');
    expectViewToggle();
  });

  it('Filter offers the portal fields for the kind', async () => {
    mount(LIMITED);
    await screen.findByText('MYR-0001');
    await expectPortalFilterFields('sample_request');
  });

  it('a right click (long press) on a card opens the preview dialog', async () => {
    mount(LIMITED);
    const card = (await screen.findByText('MYR-0001')).closest('[role="link"]') as HTMLElement;
    expect(card).not.toBeNull();
    fireEvent.contextMenu(card);
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getAllByText('MYR-0001').length).toBeGreaterThanOrEqual(1);
    expect(within(dialog).getByText('Document number')).toBeInTheDocument();
    expect(within(dialog).getAllByText('Buyer One').length).toBeGreaterThanOrEqual(1);
    expect(within(dialog).getByRole('button', { name: 'Duplicate' })).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: 'Open' })).toBeInTheDocument();
  });

  it('Create is labelled "Create" and sits on the Filter row', async () => {
    mount(LIMITED);
    await screen.findByText('MYR-0001');
    expectCreateOnFilterRow('MYR-0001');
  });

  it('hides Create when .add is not held', async () => {
    mount(['projects.sample_requests.view_own']);
    await screen.findByText('MYR-0001');
    expect(screen.queryByLabelText('Create')).toBeNull();
  });

  it('carries no portal chrome', async () => {
    mount(LIMITED);
    await screen.findByText('MYR-0001');
    expectNoPortalChrome('sample_request');
  });
});

describe('Sample Request list, staff user (pin)', () => {
  it('still gets the DataGrid and never asks my-requests for the list', async () => {
    mount(STAFF);
    expect(await screen.findByText('STAFF-0001')).toBeInTheDocument();
    expect(screen.getByRole('table')).toBeInTheDocument();
    expect(screen.queryByLabelText('Board view')).toBeNull();
    expect(urlsOf(apiFetch).some((u) => u.includes('/my-requests/submissions/sample_request'))).toBe(false);
  });
});
