/**
 * OCN-ORDER-CHANGE-NOTICE round 4 (review and security fixes, lead rulings): the detail page's new
 * behaviour. Same harness as OrderChangeNoticeDetail.test.tsx.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
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
  };
});

import OrderChangeNoticeDetail from './OrderChangeNoticeDetail';
import { OCN_ID, UUID_RE, ocnDetail } from './ocnTestData';

const VIEW = 'procurement.order_change_notices.view';
const CREATE = 'procurement.order_change_notices.create';
const EDIT = 'procurement.order_change_notices.edit';
const APPROVE = 'procurement.order_change_notices.approve';
const PROCESS = 'procurement.order_change_notices.process';

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
const MAIN = [/^submit$/i, /^send for approval$/i, /^approve$/i, /^mark done$/i];

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

const SO_ID = '4a1b2c3d-0000-4000-8000-0000000000aa';
const PO_ID = '4a1b2c3d-0000-4000-8000-0000000000bb';
const AMENDMENT_ID = '4a1b2c3d-0000-4000-8000-0000000000cc';

function amendmentBorn(over: Record<string, unknown> = {}) {
  return ocnDetail({
    source: 'amendment',
    lines: [],
    project_sales_order_id: SO_ID,
    purchase_order_id: PO_ID,
    so_ref: 'SO397450',
    po_number: 'HQ/26/01/121',
    amendment_id: AMENDMENT_ID,
    amendment_status: 'proposed',
    change_table_json: {
      rows: [
        {
          so_line_id: 'l3', line_no: 3, product_code: 'SRTWC8613-RL', description: 'WC S-TRAP',
          verb: 'DELAY', field: 'delivery_date', from_value: '2026-07-01', to_value: '2027-01-07', qty: '135',
        },
      ],
      verb_summary: { DELAY: 1 },
      unmatched: [],
    },
    ...over,
  });
}

describe('round 4: the linked amendment on the Details tab (review B1)', () => {
  it('shows the change rows and the sales order and PO by number as links, never an id', async () => {
    mount(amendmentBorn(), []);
    await ready();
    expect(screen.getByText('Linked amendment')).toBeTruthy();
    const so = screen.getByRole('link', { name: 'SO397450' });
    expect(so.getAttribute('href')).toContain(`/sales-orders/${SO_ID}`);
    const po = screen.getByRole('link', { name: 'HQ/26/01/121' });
    expect(po.getAttribute('href')).toContain(`/pos/${PO_ID}`);
    expect(screen.getAllByText(/SRTWC8613-RL/).length).toBeGreaterThan(0);
    expect(document.body.textContent).not.toMatch(UUID_RE);
  });

  it('is not drawn for a notice raised by hand with no amendment', async () => {
    mount(ocnDetail(), []);
    await ready();
    expect(screen.queryByText('Linked amendment')).toBeNull();
  });
});

describe('round 4: files on the Details tab (review B2)', () => {
  it('offers Link Attachment on a draft to whoever may edit it', async () => {
    mount(ocnDetail({ status: 'draft' }), [CREATE]);
    await ready();
    expect(screen.getByText('Linked Attachments')).toBeTruthy();
    expect(screen.getByRole('button', { name: /link attachment/i })).toBeTruthy();
  });

  it('only lists the files once the notice is approved', async () => {
    mount(ocnDetail({ status: 'approved', approval_status: 'approved' }), [CREATE, EDIT]);
    await ready();
    expect(screen.getByText('Linked Attachments')).toBeTruthy();
    expect(screen.queryByRole('button', { name: /link attachment/i })).toBeNull();
  });
});

describe('round 4: Done needs the process grant (security M3)', () => {
  it('edit alone shows no Mark done; process does', async () => {
    mount(ocnDetail({ status: 'approved', approval_status: 'approved' }), [EDIT]);
    await ready();
    expect(button(/^mark done$/i)).toBeNull();
    cleanup();
    mount(ocnDetail({ status: 'approved', approval_status: 'approved' }), [PROCESS]);
    await ready();
    expect(button(/^mark done$/i)).toBeTruthy();
  });
});

describe('round 4: the void reason follows the backend rule (m14)', () => {
  it('keeps Void disabled until the reason has three characters', async () => {
    mount(ocnDetail({ status: 'draft' }), [EDIT]);
    await ready();
    fireEvent.click(button(/^void$/i)!);
    const confirm = (await screen.findAllByRole('button', { name: /^void$/i })).at(-1) as HTMLButtonElement;
    fireEvent.change(screen.getByLabelText(/^Reason/), { target: { value: 'ab' } });
    expect(confirm.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText(/^Reason/), { target: { value: 'abc' } });
    expect(confirm.disabled).toBe(false);
  });
});

describe('round 4: the record header and empty state (m9, m10)', () => {
  it('reads the customer and PO under the number, joined by a comma, never a middle dot', async () => {
    mount(ocnDetail(), []);
    await ready();
    expect(screen.getByTestId('record-header-card')).toBeTruthy();
    expect(screen.getByText('Customer A, PO XT04/3871 (R1)')).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/\u00b7/);
  });

  it('the CS comment empty state says nothing about how the process works', async () => {
    mount(ocnDetail({ cs_comment: null }), []);
    await ready();
    const box = screen.getByText('No comment yet').parentElement as HTMLElement;
    expect(box.textContent).not.toMatch(/when|writes one|done/i);
  });

  it('has no Revisions tab until slice 2', async () => {
    mount(ocnDetail(), []);
    await ready();
    expect(screen.queryByRole('tab', { name: /^Revisions/ })).toBeNull();
  });
});
