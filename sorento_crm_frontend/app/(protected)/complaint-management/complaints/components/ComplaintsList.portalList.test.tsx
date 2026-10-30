/**
 * PORTAL-P4-REQUESTS L2 (hand test 3, owner a25895124 Q1 a / Q3 a): a salesperson limited to their own
 * complaints (`.view_own`, not `.view`) gets the PORTAL's own list body inside the CRM page: cards with a
 * card / list toggle, the portal's filter fields, long press -> preview, "Create" on the filter row, no
 * portal chrome, rows from `/api/v1/my-requests/submissions?type=complaint`. Staff keep the DataGrid.
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
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
const push = vi.hoisted(() => vi.fn());
vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return { ...actual, apiFetch: (...a: unknown[]) => apiFetch(...a) };
});
vi.mock('next/navigation', () => ({
  usePathname: () => '/complaint-management/complaints',
  useRouter: () => ({ push, replace: vi.fn(), prefetch: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
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
vi.mock('../hooks/useComplaints', () => ({
  useComplaints: () => ({
    data: { data: [{ id: 'staff-1', complaint_number: 'STAFF-0001', status: 'submitted', created_at: '2026-08-20T02:00:00' }], pagination: { total: 1, page: 1, limit: 50 } },
    isLoading: false, isFetching: false, refetch: vi.fn(),
  }),
  useExportComplaintPdf: () => ({ mutate: vi.fn(), isPending: false }),
  useDeleteComplaint: () => ({ mutateAsync: vi.fn() }),
  useBulkDeleteComplaints: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

import ComplaintsList from './ComplaintsList';

const LIMITED = ['complaint_management.complaints.view_own', 'complaint_management.complaints.add'];
const STAFF = ['complaint_management.complaints.view', 'complaint_management.complaints.add', 'complaint_management.complaints.delete'];

const PORTAL_ROW = {
  id: 'mine-1', kind: 'complaint', title: 'Leaking tap', document_number: 'MYC-0001', reference: null,
  status: 'submitted', is_editable: false, is_draft: false, created_at: '2026-08-20T02:00:00',
  product_code: 'PC-1', project_title: 'Alpha Tower', customer_name: 'Buyer One', delivery_order_number: 'DO-9001',
};

function mount(slugs: string[]) {
  held = new Set(slugs);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ComplaintsList />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  cleanup();
  window.localStorage.clear();
  apiFetch.mockReset();
  push.mockReset();
  apiFetch.mockImplementation(async (url: unknown) => {
    const u = String(url);
    if (u.includes('/api/v1/my-requests/submissions?type=complaint')) return jsonResponse({ items: [PORTAL_ROW] });
    return jsonResponse({ items: [], data: [], pagination: { total: 0, page: 1, limit: 50 } });
  });
});

describe('Complaint list, limited user: the portal list body', () => {
  it('reads its rows from my-requests, never the portal route', async () => {
    mount(LIMITED);
    expect(await screen.findByText('MYC-0001')).toBeInTheDocument();
    const urls = urlsOf(apiFetch);
    expect(urls.some((u) => u.includes('/api/v1/my-requests/submissions?type=complaint'))).toBe(true);
    expect(urls.some((u) => u.includes('/public/portal'))).toBe(false);
  });

  it('shows cards, not the staff DataGrid', async () => {
    mount(LIMITED);
    await screen.findByText('MYC-0001');
    expect(screen.queryByRole('table')).toBeNull();
    expect(screen.queryByText('STAFF-0001')).toBeNull();
  });

  it('has the card / list toggle', async () => {
    mount(LIMITED);
    await screen.findByText('MYC-0001');
    expectViewToggle();
  });

  it('Filter offers the portal fields for the kind', async () => {
    mount(LIMITED);
    await screen.findByText('MYC-0001');
    await expectPortalFilterFields('complaint');
  });

  it('a right click (long press) on a card opens the preview dialog', async () => {
    mount(LIMITED);
    const card = (await screen.findByText('MYC-0001')).closest('[role="link"]') as HTMLElement;
    expect(card).not.toBeNull();
    fireEvent.contextMenu(card);
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getAllByText('MYC-0001').length).toBeGreaterThanOrEqual(1);
    expect(within(dialog).getByText('DO-9001')).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: 'Duplicate' })).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: 'Open' })).toBeInTheDocument();
  });

  it('Create is labelled "Create" and sits on the Filter row', async () => {
    mount(LIMITED);
    await screen.findByText('MYC-0001');
    expectCreateOnFilterRow('MYC-0001');
  });

  it('hides Create when .add is not held', async () => {
    mount(['complaint_management.complaints.view_own']);
    await screen.findByText('MYC-0001');
    expect(screen.queryByLabelText('Create')).toBeNull();
  });

  it('carries no portal chrome', async () => {
    mount(LIMITED);
    await screen.findByText('MYC-0001');
    expectNoPortalChrome('complaint');
  });
});

describe('complaint list, limited user: navigation stays in the CRM', () => {
  const BASE = '/complaint-management/complaints';
  const pushed = () => push.mock.calls.map((c) => String(c[0]));

  it('a card tap goes to the CRM detail page', async () => {
    mount(LIMITED);
    const card = (await screen.findByText('MYC-0001')).closest('[role="link"]') as HTMLElement;
    fireEvent.click(card);
    expect(pushed()).toEqual([`${BASE}/mine-1`]);
  });

  it('the preview Open and Duplicate go to CRM staff pages', async () => {
    mount(LIMITED);
    const card = (await screen.findByText('MYC-0001')).closest('[role="link"]') as HTMLElement;
    fireEvent.contextMenu(card);
    let dialog = await screen.findByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Open' }));
    expect(pushed()).toEqual([`${BASE}/mine-1`]);
    fireEvent.contextMenu(card);
    dialog = await screen.findByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Duplicate' }));
    expect(pushed()).toEqual([`${BASE}/mine-1`, `${BASE}/new?from=mine-1`]);
    expect(pushed().some((u) => u.includes('/portal'))).toBe(false);
  });

  it('the list load error shows a Retry that refetches', async () => {
    apiFetch.mockReset();
    apiFetch.mockImplementation(async () => jsonResponse({ detail: 'boom' }, 500));
    mount(LIMITED);
    const retry = await screen.findByRole('button', { name: /retry/i });
    const before = urlsOf(apiFetch).filter((u) => u.includes('/my-requests/submissions')).length;
    fireEvent.click(retry);
    await waitFor(() =>
      expect(urlsOf(apiFetch).filter((u) => u.includes('/my-requests/submissions')).length).toBeGreaterThan(before),
    );
  });

  it('asks for no root-causes or resolutions lookup (hand test 2 point 1)', async () => {
    mount(LIMITED);
    await screen.findByText('MYC-0001');
    const urls = urlsOf(apiFetch);
    expect(urls.some((u) => /complaint-root-causes|complaint-resolutions/.test(u))).toBe(false);
  });
});

describe('Complaint list, staff user (pin)', () => {
  it('still gets the DataGrid and never asks my-requests for the list', async () => {
    mount(STAFF);
    expect(await screen.findByText('STAFF-0001')).toBeInTheDocument();
    expect(screen.getByRole('table')).toBeInTheDocument();
    expect(screen.queryByLabelText('Board view')).toBeNull();
    expect(urlsOf(apiFetch).some((u) => u.includes('/my-requests/submissions'))).toBe(false);
  });
});
