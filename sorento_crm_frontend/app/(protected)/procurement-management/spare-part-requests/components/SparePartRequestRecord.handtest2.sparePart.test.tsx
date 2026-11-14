/**
 * SPARE-PART-ORDER-REQUEST hand-test round 2 (owner 13 Nov), red-first (Phase 2).
 *
 * F2 "how do I know the sla assignment, who needs to do this next? refer to our form like
 *    complaint, purchase request": the record page shows the active SLA stage the way the
 *    other forms do, through the shared pieces under sla-management/_shared (the tracker read
 *    is getFormSLATrackers -> GET .../conversation-sla-tracking/by-source). Those forms put the
 *    stage in an "SLA Tracking" tab (FormSLATrackingTab: Stage, Assigned To, due columns) and
 *    keep the escalation / extension banners (SlaActiveTrackerControls) above the page body.
 *    So: with one active tracker the page offers an "SLA Tracking" tab that names the assignee,
 *    the stage and the due date as dd/mm/yyyy; with no active tracker none of that is shown.
 *
 * Asserted at the HTTP seam (`apiFetch`), real hooks, real shared components.
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

vi.mock('next/navigation', () => ({
  usePathname: () => '/procurement-management/spare-part-requests/spr-1',
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    back: vi.fn(),
    prefetch: vi.fn(),
    refresh: vi.fn(),
  }),
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
const BY_SOURCE = '/api/v1/sla-management/conversation-sla-tracking/by-source';

const detail = {
  id: 'spr-1',
  inquiry_no: 'OR-2611-0009',
  inquiry_type: 'spare_part_request',
  state: 'pending_approval',
  currency: 'MYR',
  needed_by: '2026-12-15',
  default_location: 'BRW',
  reason: 'Spare parts for the service van',
  requested_by: 'u-1',
  requested_by_name: 'ZZT Alice',
  submitted_at: '2026-11-13T02:00:00',
  can_decide: false,
  can_edit: true,
  can_revise: false,
  total: '50',
  lines: [],
};

const tracker = (over: Record<string, unknown> = {}) => ({
  id: 'trk-1',
  source_entity_type: 'spare_part_request',
  source_entity_id: 'spr-1',
  is_resolved: false,
  is_responded: false,
  current_tier: 1,
  team_set_code: 'ZZT-ORDER-L1',
  assigned_to_id: 'u-9',
  assigned_user_name: 'ZZT Bob Approver',
  initiated_at: '2026-11-13T02:00:00',
  due_at: '2026-11-19T08:00:00',
  due_at_resolution: '2026-11-20T08:00:00',
  resolution_due_at: '2026-11-20T08:00:00',
  event_logs: [],
  ...over,
});

let trackers: unknown[] = [];
const calls: string[] = [];
const ok = (b: unknown, status = 200) =>
  new Response(JSON.stringify(b), { status, headers: { 'content-type': 'application/json' } });
const apiFetch = vi.fn(async (url: string) => {
  calls.push(url);
  const path = url.split('?')[0];
  if (path === BY_SOURCE) return ok(trackers);
  if (path === `${SPR}/spr-1`) return ok(detail);
  if (path.endsWith('/history')) return ok({ events: [] });
  if (path.endsWith('/attachments/lookup')) return ok({});
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

function openSlaTab() {
  const tab = screen.queryByRole('tab', { name: /sla/i });
  if (!tab) return false;
  fireEvent.mouseDown(tab);
  fireEvent.click(tab);
  return true;
}

beforeEach(() => {
  cleanup();
  calls.length = 0;
  trackers = [];
  vi.clearAllMocks();
});

describe('F2: the SLA assignment on the request record page', () => {
  it('reads the trackers of this request through the by-source endpoint', async () => {
    trackers = [tracker()];
    mount();
    await screen.findByText('OR-2611-0009');
    await waitFor(() => {
      const hit = calls.find((c) => c.startsWith(BY_SOURCE));
      expect(hit, 'GET by-source fired').toBeTruthy();
      expect(hit).toContain('source_entity_type=spare_part_request');
      expect(hit).toContain('source_entity_id=spr-1');
    });
  });

  it('offers an SLA tab, as the other forms do', async () => {
    trackers = [tracker()];
    mount();
    await screen.findByText('OR-2611-0009');
    expect(await screen.findByRole('tab', { name: /sla/i })).toBeTruthy();
  });

  it('with one active tracker it names the assignee, the stage and the due date (dd/mm/yyyy)', async () => {
    trackers = [tracker()];
    mount();
    await screen.findByText('OR-2611-0009');
    await waitFor(() => expect(openSlaTab(), 'an SLA tab to open').toBe(true));
    expect((await screen.findAllByText(/ZZT Bob Approver/)).length).toBeGreaterThan(0);
    expect((await screen.findAllByText(/ZZT-ORDER-L1/)).length).toBeGreaterThan(0);
    expect((await screen.findAllByText(/20\/11\/2026/)).length).toBeGreaterThan(0);
  });

  it('with no active tracker it shows no assignee, stage or due date for it', async () => {
    trackers = [tracker({ is_resolved: true, resolved_at: '2026-11-14T02:00:00' })];
    mount();
    await screen.findByText('OR-2611-0009');
    await waitFor(() => expect(calls.some((c) => c.startsWith(BY_SOURCE))).toBe(true));
    openSlaTab();
    await waitFor(() => expect(screen.queryByText(/ZZT Bob Approver/)).toBeNull());
    expect(screen.queryByText(/20\/11\/2026/)).toBeNull();
    expect(screen.queryByText(/now assigned to/i)).toBeNull();
  });

  it('shows the escalation banner for an escalated active tracker, like Complaint', async () => {
    trackers = [
      tracker({
        escalation_reason: 'auto: no response in time',
        escalated_at: '2026-11-15T02:00:00',
        current_tier: 2,
      }),
    ];
    mount();
    await screen.findByText('OR-2611-0009');
    expect(await screen.findByText(/SLA escalated/i)).toBeTruthy();
    expect(screen.getAllByText(/ZZT Bob Approver/).length).toBeGreaterThan(0);
  });
});
