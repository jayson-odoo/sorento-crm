/**
 * SPARE-PART-ORDER-REQUEST review round 2, red-first (Phase 2).
 *
 * R3 (review M3; owner rule "open a record from a filtered, sorted list: prev/next is there";
 *    CLAUDE.md "detail pages carry prev/next record navigation"): the record page carries the
 *    standard pager (DetailActions `pager` over useListPager, as OrderInquiryDetail.tsx does).
 *    Opened from the list filtered to Pending approval, it walks THAT list: the page's list GET
 *    carries the filter, the counter reads "2 of 3", Next opens the next request's record page
 *    with the list state kept in the URL.
 * R7 (review S4) one status vocabulary: for a raised (and a done) request the header pill AND
 *    the General tab's Approval card both read "Approved", never "Raised" / "Done".
 *
 * Asserted at the HTTP seam (`apiFetch`) with the real hooks and services.
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
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

/** The URL the list's rowHref writes: page 1 of 25, sorted by number, filtered to pending. */
const SEARCH = 'page=1&limit=25&sort=inquiry_no&dir=asc&status=pending_approval';
const push = vi.fn();
vi.mock('next/navigation', () => ({
  usePathname: () => '/procurement-management/spare-part-requests/spr-1',
  useRouter: () => ({ push, replace: vi.fn(), back: vi.fn(), prefetch: vi.fn(), refresh: vi.fn() }),
  useSearchParams: () => new URLSearchParams(SEARCH),
  useParams: () => ({ id: 'spr-1' }),
}));
vi.mock('next-auth/react', () => ({
  useSession: () => ({ data: { user: { id: 'u-1', name: 'ZZT Alice' } }, status: 'authenticated' }),
  SessionProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));
vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => true,
  useHasAnyPermission: () => true,
  usePermissions: () => ({ permissionSet: new Set(), permissions: [], isLoading: false, isError: false }),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));
vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: vi.fn(),
  cancelPendingAction: vi.fn(),
  getCurrentPendingAction: vi.fn().mockResolvedValue({ pending: null, last_outcome: null }),
}));
vi.mock('@/components/common/deferredToast', () => ({
  deferredToast: () => 'pending-action-1',
  dismissDeferredToast: vi.fn(),
}));

const SPR = '/api/v1/project-sales/spare-part-requests';

function detail(over: Record<string, unknown> = {}) {
  return {
    id: 'spr-1',
    inquiry_no: 'OI-2611-0009',
    inquiry_type: 'spare_part_request',
    state: 'pending_approval',
    currency: 'MYR',
    needed_by: '2026-12-15',
    default_location: 'BRW',
    reason: 'Spare parts for the service van',
    requested_by: 'u-1',
    requested_by_name: 'ZZT Alice',
    submitted_at: '2026-11-13T02:00:00',
    approved_at: null,
    approved_by: null,
    approved_by_name: null,
    reject_reason: null,
    can_decide: false,
    can_edit: true,
    can_revise: false,
    total: '50',
    lines: [],
    ...over,
  };
}

const listRow = (id: string, no: string) => ({
  id,
  inquiry_no: no,
  state: 'pending_approval',
  requested_by: 'u-1',
  requested_by_name: 'ZZT Alice',
  needed_by: '2026-12-15',
  line_count: 1,
  total: '50',
  currency: 'MYR',
  submitted_at: '2026-11-13T02:00:00',
});

let current = detail();
const calls: string[] = [];
const ok = (b: unknown, status = 200) =>
  new Response(JSON.stringify(b), { status, headers: { 'content-type': 'application/json' } });
const apiFetch = vi.fn(async (url: string) => {
  calls.push(url);
  const path = url.split('?')[0];
  if (path === SPR)
    return ok({
      data: [
        listRow('spr-0', 'OI-2611-0008'),
        listRow('spr-1', 'OI-2611-0009'),
        listRow('spr-2', 'OI-2611-0010'),
      ],
      pagination: { total: 3, page: 1, limit: 25 },
    });
  if (path === `${SPR}/spr-1`) return ok(current);
  if (path.endsWith('/history')) return ok({ events: [] });
  if (path.endsWith('/attachments/lookup')) return ok({});
  if (path.endsWith('/lines')) return ok([]);
  return ok({ data: [], pagination: { total: 0, page: 1, limit: 25 } });
});
vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  apiFetch: (...a: [string, RequestInit?]) => apiFetch(a[0]),
}));

import { SparePartRequestRecord } from './SparePartRequestRecord';

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SparePartRequestRecord id="spr-1" />
    </QueryClientProvider>,
  );
}

const listGets = () =>
  calls.filter((u) => u.split('?')[0] === SPR).map((u) => new URLSearchParams(u.split('?')[1] ?? ''));

beforeEach(() => {
  cleanup();
  calls.length = 0;
  vi.clearAllMocks();
  current = detail();
});

describe('R3 (M3): the record page carries prev / next over the list it came from', () => {
  it('shows the pager with the position on the filtered list', async () => {
    mount();
    await screen.findAllByText('OI-2611-0009');
    const next = await screen.findByRole('button', { name: /^next /i }, { timeout: 3000 });
    expect(next).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^previous /i })).toBeInTheDocument();
    expect(await screen.findByLabelText('2 of 3 records')).toBeInTheDocument();
  });

  it("walks the list's filtered, sorted order (the list GET carries the filter)", async () => {
    mount();
    await screen.findAllByText('OI-2611-0009');
    await waitFor(() => expect(listGets().length, 'the pager reads the list page').toBeGreaterThan(0));
    const params = listGets()[0];
    expect(params.getAll('state')).toEqual(['pending_approval']);
    expect(params.get('sort')).toBe('inquiry_no');
    expect(params.get('dir')).toBe('asc');
  });

  it("Next opens the next request's record page, keeping the list state", async () => {
    mount();
    const next = await screen.findByRole('button', { name: /^next /i }, { timeout: 3000 });
    await waitFor(() => expect(next).not.toBeDisabled());
    fireEvent.click(next);
    await waitFor(() => expect(push).toHaveBeenCalled());
    const href = String(push.mock.calls[0][0]);
    expect(href.startsWith('/procurement-management/spare-part-requests/spr-2?')).toBe(true);
    const query = new URLSearchParams(href.split('?')[1]);
    expect(query.get('status')).toBe('pending_approval');
    expect(query.get('sort')).toBe('inquiry_no');
  });
});

async function openGeneral() {
  const tab = screen.getAllByRole('tab').find((t) => t.textContent?.trim().startsWith('General'));
  expect(tab).toBeTruthy();
  fireEvent.mouseDown(tab!, { button: 0 });
  fireEvent.click(tab!);
  return screen.findByRole('region', { name: 'Approval' });
}

describe('R7 (S4): one word for the approved state on the whole record page', () => {
  it.each(['raised', 'actioned'])(
    'a %s request reads Approved on the pill and in the General Approval card',
    async (state) => {
      current = detail({
        state,
        can_edit: false,
        approved_at: '2026-11-13T05:00:00',
        approved_by_name: 'ZZT Approver',
      });
      mount();
      await screen.findAllByText('OI-2611-0009');
      expect(screen.getAllByText('Approved').length).toBeGreaterThan(0);

      const approval = await openGeneral();
      const status = within(approval).getByText('Status').nextElementSibling;
      expect(status?.textContent?.trim(), 'the Approval card Status').toBe('Approved');
      expect(within(approval).queryByText('Raised')).toBeNull();
      expect(within(approval).queryByText('Done')).toBeNull();
    },
  );

  it('a pending request reads Pending approval in both places (guard)', async () => {
    mount();
    await screen.findAllByText('OI-2611-0009');
    const approval = await openGeneral();
    expect(within(approval).getByText('Status').nextElementSibling?.textContent?.trim()).toBe(
      'Pending approval',
    );
  });
});
