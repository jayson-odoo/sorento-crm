/**
 * SPARE-PART-ORDER-REQUEST hand-test round (owner 13 Nov), red-first (Phase 2). UAC G3.
 *
 * F3 SparePartRequestsList (app/(protected)/procurement-management/spare-part-requests/
 *    components/SparePartRequestsList.tsx): a standard DataGrid over
 *    GET /api/v1/project-sales/spare-part-requests with the columns Number, Status, Requested by,
 *    Needed by, Lines, Total, Submitted; a toolbar with search, Filters, Columns and a "Create"
 *    button shown only with `procurement.spare_part_requests.create`; a row click opens the
 *    request's record page /procurement-management/spare-part-requests/<id>.
 *
 * Asserted at the HTTP seam (`apiFetch`) with the real hooks and service.
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
class IntersectionObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { IntersectionObserver: unknown }).IntersectionObserver =
  IntersectionObserverStub;
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}
Element.prototype.scrollIntoView = vi.fn();

const push = vi.fn();
vi.mock('next/navigation', () => ({
  usePathname: () => '/procurement-management/spare-part-requests',
  useRouter: () => ({ push, replace: vi.fn(), back: vi.fn(), prefetch: vi.fn(), refresh: vi.fn() }),
  useSearchParams: () => new URLSearchParams(''),
  useParams: () => ({}),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));
vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));
const granted = vi.hoisted(() => ({ slugs: new Set<string>() }));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => granted.slugs.has(slug),
  useHasAnyPermission: (slugs: string[]) => slugs.some((s) => granted.slugs.has(s)),
  usePermissions: () => ({
    permissionSet: granted.slugs,
    permissions: [...granted.slugs],
    isLoading: false,
    isError: false,
  }),
}));
vi.mock('@/services/userSelectService', () => ({
  getUserLookup: vi.fn().mockResolvedValue([{ id: 'u-1', name: 'ZZT Alice' }]),
  getUsersSelect: vi.fn().mockResolvedValue([{ id: 'u-1', name: 'ZZT Alice' }]),
}));

const LIST = '/api/v1/project-sales/spare-part-requests';
const ROW = {
  id: 'spr-1',
  inquiry_no: 'OI-2611-0009',
  state: 'pending_approval',
  requested_by: 'u-1',
  requested_by_name: 'ZZT Alice',
  needed_by: '2026-12-15',
  line_count: 2,
  total: '300',
  currency: 'MYR',
  submitted_at: '2026-11-13T02:00:00',
};

const calls: string[] = [];
const ok = (b: unknown, status = 200) =>
  new Response(JSON.stringify(b), { status, headers: { 'content-type': 'application/json' } });
const apiFetch = vi.fn(async (url: string) => {
  calls.push(url);
  if (url === LIST || url.startsWith(`${LIST}?`))
    return ok({ data: [ROW], pagination: { total: 1, page: 1, limit: 25 } });
  return ok(url.includes('select') ? { data: [] } : {});
});
vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  apiFetch: (...a: [string, RequestInit?]) => apiFetch(a[0]),
}));

import * as ListModule from './SparePartRequestsList';

const SparePartRequestsList = ((ListModule as Record<string, unknown>).SparePartRequestsList ??
  (ListModule as Record<string, unknown>).default) as React.ComponentType;

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SparePartRequestsList />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  cleanup();
  calls.length = 0;
  vi.clearAllMocks();
  granted.slugs = new Set(['procurement.spare_part_requests.create']);
});

describe('F3 (G3): the Spare Part Requests list', () => {
  it('reads the spare part requests list endpoint and shows the row', async () => {
    mount();
    expect(await screen.findByText('OI-2611-0009')).toBeInTheDocument();
    expect(calls.some((u) => u === LIST || u.startsWith(`${LIST}?`))).toBe(true);
    expect(calls.some((u) => u.includes('/order-inquiry-headers'))).toBe(false);
  });

  it('has the columns Number, Status, Requested by, Needed by, Lines, Total, Submitted', async () => {
    mount();
    await screen.findByText('OI-2611-0009');
    const headers = screen.getAllByRole('columnheader').map((h) => h.textContent?.trim() ?? '');
    for (const name of ['Number', 'Status', 'Requested by', 'Needed by', 'Lines', 'Total', 'Submitted']) {
      expect(headers.some((h) => h.startsWith(name)), `column ${name} in ${headers.join(' | ')}`).toBe(true);
    }
    expect(screen.getByText('Pending approval')).toBeInTheDocument();
    expect(screen.getByText('ZZT Alice')).toBeInTheDocument();
  });

  it('the toolbar has search, Filters, Columns and Create', async () => {
    mount();
    await screen.findByText('OI-2611-0009');
    expect(
      screen.queryByRole('searchbox') ?? screen.getByPlaceholderText(/search/i),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^filters/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /columns/i })).toBeInTheDocument();
    const asLink = screen.queryByRole('link', { name: /^create$/i });
    if (asLink) {
      expect(asLink.getAttribute('href')).toBe('/procurement-management/spare-part-requests/new');
    } else {
      fireEvent.click(screen.getByRole('button', { name: /^create$/i }));
      expect(push).toHaveBeenCalledWith('/procurement-management/spare-part-requests/new');
    }
  });

  it('there is no Create without the create permission', async () => {
    granted.slugs = new Set(['projects.projects.view']);
    mount();
    await screen.findByText('OI-2611-0009');
    expect(screen.queryByRole('button', { name: /^create$/i })).toBeNull();
    expect(screen.queryByRole('link', { name: /^create$/i })).toBeNull();
  });

  it('a row click opens the request record page', async () => {
    mount();
    fireEvent.click(await screen.findByText('ZZT Alice'));
    await waitFor(() => expect(push).toHaveBeenCalled());
    const href = String(push.mock.calls[0][0]);
    expect(href.startsWith('/procurement-management/spare-part-requests/spr-1')).toBe(true);
  });
});
