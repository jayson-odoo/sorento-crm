/**
 * OCN-ORDER-CHANGE-NOTICE round 5 (lead rulings N3, N7): who sees Void, and a file uploaded straight
 * onto the notice from the Details tab. Same harness as OrderChangeNoticeDetail.round4.test.tsx.
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

const state = vi.hoisted(() => ({
  perms: new Set<string>(),
  userId: '2f6b9d38-5e41-4c97-8a20-4d7c1b0e6f06',
  get: vi.fn(),
  submit: vi.fn(),
  upload: vi.fn(),
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
vi.mock('@/app/(protected)/sla-management/_shared/FormSLATrackingTab', () => ({
  default: (p: { sourceEntityType: string; sourceEntityId: string }) => (
    <div data-testid="sla-tab">{`${p.sourceEntityType}:${p.sourceEntityId}`}</div>
  ),
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
vi.mock('@/app/(protected)/sla-management/_shared/formSLAService', () => ({
  getFormSLATrackers: vi.fn(async () => []),
  escalateFormTracking: vi.fn(),
}));
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
    uploadOrderChangeNoticeAttachment: (...a: unknown[]) => state.upload(...a),
  };
});

import OrderChangeNoticeDetail from './OrderChangeNoticeDetail';
import { OCN_ID, ocnDetail } from './ocnTestData';

const VIEW = 'procurement.order_change_notices.view';
const CREATE = 'procurement.order_change_notices.create';
const EDIT = 'procurement.order_change_notices.edit';

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
const button = (name: RegExp) => screen.queryByRole('button', { name });

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

const OTHER = '9a8b7c6d-0000-4000-8000-0000000000ee';

describe('round 5: Void shows only to who may void (N7, the backend edit rule)', () => {
  it('the raiser without the create grant sees no Void', async () => {
    mount(ocnDetail({ status: 'draft' }), []);
    await ready();
    expect(button(/^void$/i)).toBeNull();
  });

  it('the raiser with the create grant sees Void on their own notice', async () => {
    mount(ocnDetail({ status: 'draft' }), [CREATE]);
    await ready();
    expect(button(/^void$/i)).toBeTruthy();
  });

  it('create alone gives no Void on someone else\u2019s notice', async () => {
    mount(ocnDetail({ status: 'draft', created_by: OTHER }), [CREATE]);
    await ready();
    expect(button(/^void$/i)).toBeNull();
  });

  it('an editor sees Void on anyone\u2019s notice', async () => {
    mount(ocnDetail({ status: 'draft', created_by: OTHER }), [EDIT]);
    await ready();
    expect(button(/^void$/i)).toBeTruthy();
  });
});

describe('round 5: a file uploaded straight onto the notice (N3)', () => {
  it('a draft the user may edit offers the drop zone, and a chosen file goes up through the service', async () => {
    state.upload.mockResolvedValue({});
    const { container } = mount(ocnDetail({ status: 'draft' }), [CREATE]);
    await ready();
    expect(screen.getByRole('button', { name: /choose file/i })).toBeTruthy();
    const input = container.ownerDocument.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(['%PDF-1.4'], 'revised-po.pdf', { type: 'application/pdf' });
    fireEvent.change(input, { target: { files: [file] } });
    await waitFor(() => expect(state.upload).toHaveBeenCalledWith(OCN_ID, file));
  });

  it('a reader gets no drop zone', async () => {
    mount(ocnDetail({ status: 'draft', created_by: OTHER }), []);
    await ready();
    expect(screen.getByText('Linked Attachments')).toBeTruthy();
    expect(screen.queryByRole('button', { name: /choose file/i })).toBeNull();
  });
});
