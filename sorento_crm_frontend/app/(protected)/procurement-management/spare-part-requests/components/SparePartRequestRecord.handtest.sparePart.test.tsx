/**
 * SPARE-PART-ORDER-REQUEST hand-test round (owner 13 Nov), red-first (Phase 2). UAC G3, G5.
 *
 * F4 SparePartRequestRecord (app/(protected)/procurement-management/spare-part-requests/
 *    components/SparePartRequestRecord.tsx, rendered by [id]/page.tsx with the `id`):
 *    a header with the number and a status pill (Draft / Pending approval / Approved /
 *    Rejected), the tabs Lines, General, History; once raised a "Raised to purchasing" link to
 *    /project-sales/order-inquiries/<id>; Edit (to .../spare-part-requests/<id>/edit) for the
 *    requester while Draft, Pending approval or Rejected (the detail's `can_edit`), never once
 *    raised.
 *
 * Asserted at the HTTP seam (`apiFetch`): the detail is GET /spare-part-requests/<id>.
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, fireEvent } from '@testing-library/react';
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
  usePathname: () => '/procurement-management/spare-part-requests/spr-1',
  useRouter: () => ({ push, replace: vi.fn(), back: vi.fn(), prefetch: vi.fn(), refresh: vi.fn() }),
  useSearchParams: () => new URLSearchParams(''),
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
    lines: [
      {
        id: 'row-1',
        product_id: 'prod-1',
        item_code: 'SP-SEAL-40',
        product_name: 'Pump seal',
        description: 'Pump seal, left side',
        stock_location: 'BRW',
        qty: '2',
        unit_price: '25',
        total: '50',
        requested_qty: '2',
        requested_unit_price: '25',
        state: 'draft',
        ack_state: 'awaiting',
        photo_changes: { added: 0, removed: 0 },
      },
    ],
    ...over,
  };
}

let current = detail();
const calls: string[] = [];
const ok = (b: unknown, status = 200) =>
  new Response(JSON.stringify(b), { status, headers: { 'content-type': 'application/json' } });
const apiFetch = vi.fn(async (url: string) => {
  calls.push(url);
  const path = url.split('?')[0];
  if (path === `${SPR}/spr-1`) return ok(current);
  if (path.endsWith('/history')) return ok({ events: [] });
  if (path.endsWith('/attachments/lookup')) return ok({});
  if (path.endsWith('/spr-1')) return ok(current);
  return ok({ data: [], pagination: { total: 0, page: 1, limit: 25 } });
});
vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  apiFetch: (...a: [string, RequestInit?]) => apiFetch(a[0]),
}));

import * as RecordModule from './SparePartRequestRecord';

const SparePartRequestRecord = ((RecordModule as Record<string, unknown>).SparePartRequestRecord ??
  (RecordModule as Record<string, unknown>).default) as React.ComponentType<{ id: string }>;

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SparePartRequestRecord id="spr-1" />
    </QueryClientProvider>,
  );
}

const editTarget = (): string | null => {
  const link = screen.queryByRole('link', { name: /^edit$/i });
  if (link) return link.getAttribute('href');
  const button = screen.queryByRole('button', { name: /^edit$/i });
  if (!button) return null;
  fireEvent.click(button);
  return push.mock.calls.length ? String(push.mock.calls[0][0]) : 'clicked-without-navigation';
};

beforeEach(() => {
  cleanup();
  calls.length = 0;
  vi.clearAllMocks();
  current = detail();
});

describe('F4 (G3): the spare part request record page', () => {
  it('reads the request detail and heads the page with its number and status pill', async () => {
    mount();
    expect((await screen.findAllByText('OI-2611-0009')).length).toBeGreaterThan(0);
    expect(calls.some((u) => u.split('?')[0] === `${SPR}/spr-1`)).toBe(true);
    expect(screen.getAllByText('Pending approval').length).toBeGreaterThan(0);
  });

  it('has the tabs Lines, General and History', async () => {
    mount();
    await screen.findAllByText('OI-2611-0009');
    const tabs = screen.getAllByRole('tab').map((t) => t.textContent?.trim() ?? '');
    for (const name of ['Lines', 'General', 'History']) {
      expect(tabs.some((t) => t.startsWith(name)), `tab ${name} in ${tabs.join(' | ')}`).toBe(true);
    }
  });

  it.each([
    ['draft', 'Draft'],
    ['rejected', 'Rejected'],
    ['raised', 'Approved'],
  ])('a %s request reads %s on its pill', async (state, label) => {
    current = detail({ state, can_edit: state !== 'raised' });
    mount();
    await screen.findAllByText('OI-2611-0009');
    expect(screen.getAllByText(label).length).toBeGreaterThan(0);
  });

  it('once raised the header links "Raised to purchasing" to the order inquiry', async () => {
    current = detail({ state: 'raised', can_edit: false, approved_at: '2026-11-13T05:00:00' });
    mount();
    const link = await screen.findByRole('link', { name: /raised to purchasing/i });
    expect(link.getAttribute('href')).toBe('/project-sales/order-inquiries/spr-1');
  });

  it('before it is raised there is no "Raised to purchasing"', async () => {
    mount();
    await screen.findAllByText('OI-2611-0009');
    expect(screen.queryByText(/raised to purchasing/i)).toBeNull();
  });

  it.each(['draft', 'pending_approval', 'rejected'])(
    'the requester can Edit while %s',
    async (state) => {
      current = detail({ state, can_edit: true });
      mount();
      await screen.findAllByText('OI-2611-0009');
      expect(editTarget()).toBe('/procurement-management/spare-part-requests/spr-1/edit');
    },
  );

  it('no Edit once raised', async () => {
    current = detail({ state: 'raised', can_edit: false });
    mount();
    await screen.findAllByText('OI-2611-0009');
    expect(editTarget()).toBeNull();
  });
});
