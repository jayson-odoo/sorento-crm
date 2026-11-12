/**
 * OCN-ORDER-CHANGE-NOTICE round 7 (browser pass blocker): the SLA tab on the notice detail renders
 * instead of freezing the page. The REAL FormSLATrackingTab is mounted (the other harnesses stub
 * it), with its tracker read answered at the service seam.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
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

const state = vi.hoisted(() => ({
  perms: new Set<string>(),
  userId: '2f6b9d38-5e41-4c97-8a20-4d7c1b0e6f06',
  get: vi.fn(),
  submit: vi.fn(),
  trackers: vi.fn(),
}));

// Next's router syncs history.replaceState into useSearchParams (useUrlTab relies on it), so a tab
// click really switches the tab here.
vi.mock('next/navigation', async () => {
  const React = await import('react');
  const listeners = new Set<() => void>();
  const original = window.history.replaceState.bind(window.history);
  window.history.replaceState = (data: unknown, unused: string, url?: string | URL | null) => {
    original(data, unused, url);
    listeners.forEach((l) => l());
  };
  const subscribe = (l: () => void) => {
    listeners.add(l);
    return () => listeners.delete(l);
  };
  return {
    useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
    usePathname: () => window.location.pathname,
    useSearchParams: () => {
      const search = React.useSyncExternalStore(subscribe, () => window.location.search);
      return React.useMemo(() => new URLSearchParams(search), [search]);
    },
  };
});
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => state.perms.has(slug),
  usePermissions: () => ({ permissions: [], permissionSet: state.perms, isLoading: false }),
}));
vi.mock('@/hooks/useEffectiveUserId', () => ({ useEffectiveUserId: () => state.userId }));
vi.mock('@/hooks/useDeferredAction', () => ({
  useDeferredAction: () => ({ countdown: null, isBlocked: false, start: vi.fn() }),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

vi.mock('@/components/audit/AuditTrail', () => ({
  default: (p: { entityType: string; entityId: string }) => (
    <div data-testid="audit-trail">{`${p.entityType}:${p.entityId}`}</div>
  ),
}));
vi.mock('@/components/common/comments/FormComments', () => ({
  FormComments: (p: { kind: string; entityId: string }) => (
    <div data-testid="conversation">{`${p.kind}:${p.entityId}`}</div>
  ),
}));
vi.mock('@/components/common/RevisionTimeline', () => ({
  default: () => <div data-testid="revisions" />,
  RevisionTimeline: () => <div data-testid="revisions" />,
}));
vi.mock('@/app/(protected)/sla-management/_shared/useHandlingLock', () => ({
  useHandlingLock: () => ({
    state: 'not_escalated', businessCtasEnabled: true, tracker: null, banner: null,
    claim: vi.fn(), takeOver: vi.fn(), release: vi.fn(), refresh: vi.fn(), isMutating: false,
  }),
}));
vi.mock('@/app/(protected)/sla-management/_shared/HandlingLockBanner', () => ({ HandlingLockBanner: () => null }));
vi.mock('@/app/(protected)/sla-management/_shared/HandlingLockActions', () => ({
  HandlingLockReleaseMenuItem: () => null,
}));
vi.mock('@/app/(protected)/sla-management/_shared/SlaActiveTrackerControls', () => ({
  SlaActiveTrackerControls: () => null,
}));
vi.mock('@/app/(protected)/sla-management/_shared/SlaExtendAction', () => ({
  SlaExtendMenuItem: () => null,
  SlaExtendDialog: () => null,
}));
vi.mock('@/app/(protected)/sla-management/_shared/useFormAction', () => ({
  useFormAction: () => ({
    view: { kind: 'idle' }, ctasDisabled: false, cancel: vi.fn(), undo: vi.fn(), refresh: vi.fn(), isMutating: false,
  }),
}));
vi.mock('@/app/(protected)/sla-management/_shared/formSLAService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/app/(protected)/sla-management/_shared/formSLAService')>();
  return { ...actual, getFormSLATrackers: (...a: unknown[]) => state.trackers(...a), escalateFormTracking: vi.fn() };
});
vi.mock('@/components/common/ListPager', () => ({ default: () => null }));
vi.mock('@/components/common/RecordNavigation', () => ({ default: () => null, RecordNavigation: () => null }));
vi.mock('@/components/common/DetailActions', () => ({
  default: ({ gear, primary }: { gear?: React.ReactNode; primary?: React.ReactNode }) => (
    <div>
      {gear}
      {primary}
    </div>
  ),
}));
vi.mock('@/components/common/DetailActionsMenu', () => ({
  DetailActionsMenu: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
vi.mock('@/components/ui/dropdown-menu', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/components/ui/dropdown-menu')>();
  return {
    ...actual,
    DropdownMenuItem: ({ children, onSelect }: { children: React.ReactNode; onSelect?: () => void }) => (
      <button type="button" onClick={() => onSelect?.()}>{children}</button>
    ),
    DropdownMenuSeparator: () => null,
    DropdownMenuLabel: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
    DropdownMenuGroup: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  };
});

vi.mock('../services/orderChangeNoticeService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../services/orderChangeNoticeService')>();
  return {
    ...actual,
    getOrderChangeNotice: (...a: unknown[]) => state.get(...a),
    submitOrderChangeNotice: (...a: unknown[]) => state.submit(...a),
  };
});

import OrderChangeNoticeDetail from './OrderChangeNoticeDetail';
import { OCN_ID, ocnDetail } from './ocnTestData';

const VIEW = 'procurement.order_change_notices.view';

function mount(record: Record<string, unknown>, perms: string[]) {
  state.perms = new Set([VIEW, ...perms]);
  state.get.mockResolvedValue(record);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <OrderChangeNoticeDetail ocnId={OCN_ID} />
    </QueryClientProvider>,
  );
}
const ready = () => screen.findByRole('heading', { name: /OCN26-0302/ });

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  window.history.replaceState(null, '', '/procurement-management/order-change-notices/' + OCN_ID);
  vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 404, headers: { 'Content-Type': 'application/json' } })));
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const TRACKER = {
  id: 'trk-1',
  team_set_code: 'SALES_ADMIN',
  policy_name: 'Order change notice review',
  initiated_at: '2026-11-10T02:00:00Z',
  due_at: '2026-11-11T02:00:00Z',
  current_tier_started_at: '2026-11-10T02:00:00Z',
  is_responded: false,
  is_resolved: false,
  escalated_at: null,
  agent_code: null,
};

async function openSla() {
  await ready();
  fireEvent.click(screen.getByRole('tab', { name: /^SLA/ }));
}

describe('round 7: the SLA tab renders on the notice detail (browser pass blocker)', () => {
  it('with no tracker it shows the empty state', async () => {
    state.trackers.mockResolvedValue([]);
    mount(ocnDetail({ status: 'submitted' }), []);
    await openSla();
    expect(await screen.findByText(/No SLA trackers attached to this/)).toBeTruthy();
  });

  it('with one tracker it shows the tracker grid', async () => {
    state.trackers.mockResolvedValue([TRACKER]);
    mount(ocnDetail({ status: 'submitted' }), []);
    await openSla();
    expect(await screen.findByText(/1 tracker for this/)).toBeTruthy();
    expect(screen.getByText('SALES_ADMIN')).toBeTruthy();
  });
});
