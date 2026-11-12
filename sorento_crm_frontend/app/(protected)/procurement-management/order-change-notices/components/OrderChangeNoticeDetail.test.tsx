/**
 * OCN-ORDER-CHANGE-NOTICE UAC G4 (red-first): the Order Change Notice detail page.
 * Component: ./OrderChangeNoticeDetail.tsx (default export, props { ocnId: string }).
 *
 * Pattern: NewProductApplicationDetail.test.tsx (the NPA is the lifecycle template). The service
 * module is mocked at its boundary (getOrderChangeNotice, submitOrderChangeNotice); the page, its
 * hooks and the shared tab shell are the real ones, the heavy children (audit trail, SLA tab,
 * conversation, revision timeline, handling lock, pager) are stubbed.
 *
 * Which button each viewer sees on each status (UAC B1-B8, D3, G4):
 *   draft                          create   -> Submit
 *   submitted (no approval yet)    edit     -> Send for approval (main), Send back (secondary)
 *   submitted + approval pending   approve  -> Approve (main), Reject (secondary)
 *   approved                       edit     -> Mark done (main), Revise (secondary)
 *   processed_by_cs / voided       nobody   -> no workflow button
 * The secondary actions may live in the gear menu (the NPA test flattens that menu into buttons).
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
  state.get.mockResolvedValue(ocnDetail());
  state.submit.mockResolvedValue(ocnDetail({ status: 'submitted' }));
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('G4 the record header', () => {
  it('shows the number and the status pill on one line', async () => {
    mount(ocnDetail(), [CREATE]);
    const heading = await ready();
    expect(within(heading).getByText('Draft')).toBeTruthy();
  });

  it.each([
    [{ status: 'draft' }, 'Draft'],
    [{ status: 'submitted', approval_status: null }, 'Submitted'],
    [{ status: 'resubmitted', approval_status: null }, 'Resubmitted'],
    [{ status: 'submitted', approval_status: 'pending' }, 'Pending approval'],
    [{ status: 'approved', approval_status: 'approved' }, 'Approved'],
    [{ status: 'rejected', approval_status: 'rejected' }, 'Rejected'],
    [{ status: 'processed_by_cs', approval_status: 'approved' }, 'Done'],
    [{ status: 'voided', approval_status: 'voided' }, 'Voided'],
  ])('writes %j as "%s", never the raw status key', async (over, word) => {
    mount(ocnDetail(over), []);
    const heading = await ready();
    expect(within(heading).getByText(word)).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/processed_by_cs/);
  });

  it('puts the read-only metadata directly under the header, above the tabs', async () => {
    mount(ocnDetail(), []);
    await ready();
    const tablist = screen.getByRole('tablist');
    for (const label of ['Created by', 'Revision', 'Source']) {
      const node = screen.getByText(label);
      expect(
        node.compareDocumentPosition(tablist) & Node.DOCUMENT_POSITION_FOLLOWING,
        `${label} sits above the tabs`,
      ).toBeTruthy();
    }
    expect(screen.getByText('CRM')).toBeTruthy();
  });
});

describe('G4 which main button each viewer sees', () => {
  it('draft: Submit for someone who can create, and no other workflow button', async () => {
    mount(ocnDetail({ status: 'draft' }), [CREATE]);
    await ready();
    expect(button(/^submit$/i)).toBeTruthy();
    for (const other of [/^send for approval$/i, /^approve$/i, /^mark done$/i, /^send back$/i, /^reject$/i]) {
      expect(button(other), String(other)).toBeNull();
    }
  });

  it('draft: no Submit without the create permission', async () => {
    mount(ocnDetail({ status: 'draft' }), []);
    await ready();
    expect(button(/^submit$/i)).toBeNull();
  });

  it('draft: Submit sends the notice at its revision number', async () => {
    mount(ocnDetail({ status: 'draft', revision_no: 2 }), [CREATE]);
    await ready();
    fireEvent.click(button(/^submit$/i)!);
    await waitFor(() => expect(state.submit).toHaveBeenCalledWith(OCN_ID, 2));
  });

  it('submitted: Send for approval as the main button with Send back beside it, for edit', async () => {
    mount(ocnDetail({ status: 'submitted', approval_status: null }), [EDIT]);
    await ready();
    expect(button(/^send for approval$/i)).toBeTruthy();
    expect(button(/^send back$/i)).toBeTruthy();
    for (const other of [/^submit$/i, /^approve$/i, /^mark done$/i]) expect(button(other), String(other)).toBeNull();
  });

  it('resubmitted reads like submitted', async () => {
    mount(ocnDetail({ status: 'resubmitted', approval_status: null }), [EDIT]);
    await ready();
    expect(button(/^send for approval$/i)).toBeTruthy();
  });

  it('submitted: nobody without edit sees Send for approval or Send back', async () => {
    mount(ocnDetail({ status: 'submitted', approval_status: null }), [CREATE]);
    await ready();
    expect(button(/^send for approval$/i)).toBeNull();
    expect(button(/^send back$/i)).toBeNull();
  });

  it('pending approval: Approve with Reject, for the approver', async () => {
    mount(ocnDetail({ status: 'submitted', approval_status: 'pending' }), [APPROVE]);
    await ready();
    expect(button(/^approve$/i)).toBeTruthy();
    expect(button(/^reject$/i)).toBeTruthy();
    for (const other of [/^submit$/i, /^send for approval$/i, /^mark done$/i]) expect(button(other), String(other)).toBeNull();
  });

  it('pending approval: someone with only edit cannot approve or reject', async () => {
    mount(ocnDetail({ status: 'submitted', approval_status: 'pending' }), [EDIT]);
    await ready();
    expect(button(/^approve$/i)).toBeNull();
    expect(button(/^reject$/i)).toBeNull();
    expect(button(/^send for approval$/i)).toBeNull();
  });

  it('approved: Mark done as the main button, and a Revise action, for edit', async () => {
    mount(ocnDetail({ status: 'approved', approval_status: 'approved' }), [EDIT]);
    await ready();
    expect(button(/^mark done$/i)).toBeTruthy();
    expect(button(/^revise$/i)).toBeTruthy();
    for (const other of [/^submit$/i, /^send for approval$/i, /^approve$/i]) expect(button(other), String(other)).toBeNull();
  });

  it('approved is locked: no Edit link or button on the page', async () => {
    mount(ocnDetail({ status: 'approved', approval_status: 'approved' }), [EDIT, CREATE]);
    await ready();
    expect(screen.queryByRole('link', { name: /^edit$/i })).toBeNull();
    expect(button(/^edit$/i)).toBeNull();
  });

  it.each([
    ['processed_by_cs', 'approved'],
    ['voided', 'voided'],
  ])('%s: no workflow button for anyone', async (status, approval) => {
    mount(ocnDetail({ status, approval_status: approval }), [CREATE, EDIT, APPROVE]);
    await ready();
    for (const name of [...MAIN, /^revise$/i, /^send back$/i, /^reject$/i]) {
      expect(button(name), String(name)).toBeNull();
    }
  });
});

describe('G4 tabs', () => {
  it('Details, Conversation, SLA, Revisions, History, in that order', async () => {
    mount(ocnDetail(), []);
    await ready();
    const names = screen.getAllByRole('tab').map((t) => (t.textContent ?? '').trim());
    const expected = [/^Details/, /^Conversation/, /^SLA/, /^Revisions/, /^History/];
    expect(names).toHaveLength(expected.length);
    expected.forEach((re, i) => expect(names[i], `tab ${i + 1}`).toMatch(re));
  });

  it('opens on Details', async () => {
    mount(ocnDetail(), []);
    await ready();
    expect(screen.getByRole('tab', { name: /^Details/ }).getAttribute('data-state')).toBe('active');
  });

  it('the SLA tab lists this notice only (order_change_notice + its id)', async () => {
    mount(ocnDetail(), []);
    await ready();
    fireEvent.click(screen.getByRole('tab', { name: /^SLA/ }));
    expect((await screen.findByTestId('sla-tab')).textContent).toBe(`order_change_notice:${OCN_ID}`);
  });

  it('the History tab is the shared audit trail of this notice', async () => {
    mount(ocnDetail(), []);
    await ready();
    fireEvent.click(screen.getByRole('tab', { name: /^History/ }));
    expect((await screen.findByTestId('audit-trail')).textContent).toBe(`order_change_notice:${OCN_ID}`);
  });

  it('the Conversation tab is the shared form thread of this notice', async () => {
    mount(ocnDetail(), []);
    await ready();
    fireEvent.click(screen.getByRole('tab', { name: /^Conversation/ }));
    expect((await screen.findByTestId('conversation')).textContent).toBe(`order_change_notice:${OCN_ID}`);
  });
});

describe('G4 the Details tab reads like the form', () => {
  it('prints the fields in the form order with their values', async () => {
    mount(ocnDetail(), []);
    await ready();
    const order = ['Date', 'Customer', 'Customer PO no.', 'SO no.', 'Project', 'C.S. in charge', 'Sales in charge', 'Type of change'];
    const nodes = order.map((t) => screen.getAllByText(new RegExp(`^${t.replace(/\./g, '\\.')}$`))[0]);
    for (let i = 0; i < nodes.length - 1; i += 1) {
      expect(
        nodes[i].compareDocumentPosition(nodes[i + 1]) & Node.DOCUMENT_POSITION_FOLLOWING,
        `${order[i]} before ${order[i + 1]}`,
      ).toBeTruthy();
    }
    expect(screen.getByText('03/11/2026')).toBeTruthy();
    expect(screen.getAllByText('Customer A').length).toBeGreaterThan(0);
    expect(screen.getAllByText('XT04/3871 (R1)').length).toBeGreaterThan(0);
    expect(screen.getByText('Project Alpha Tower')).toBeTruthy();
    expect(screen.getByText('CS Person A')).toBeTruthy();
    expect(screen.getAllByText('Sales Person A').length).toBeGreaterThan(0);
    expect(screen.getByText('Exchange')).toBeTruthy();
    expect(screen.getAllByText('High').length).toBeGreaterThan(0);
  });

  it('shows a dash for a value that is not there (SO no.), never a made-up one', async () => {
    mount(ocnDetail({ so_no_text: null }), []);
    await ready();
    const label = screen.getAllByText(/^SO no\.$/)[0];
    expect(label.parentElement?.textContent).toMatch(/-/);
  });

  it('lists the affected lines in the line columns, with real product codes and dd/mm/yyyy dates', async () => {
    mount(ocnDetail(), []);
    await ready();
    for (const name of ['Product', 'Qty before', 'Qty after', 'Date before', 'Date after', 'Delivered', 'Remark']) {
      expect(screen.getByRole('columnheader', { name: new RegExp(`^${name}$`) }), name).toBeTruthy();
    }
    expect(screen.getByText(/ABC123-RL/)).toBeTruthy();
    expect(screen.getByText(/ABC123-SH/)).toBeTruthy();
    expect(screen.getAllByText('15/01/2027').length).toBeGreaterThan(0);
    expect(screen.getByText('Collect back 12 sets')).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/\b\d{4}-\d{2}-\d{2}\b/);
  });

  it('shows the description', async () => {
    mount(ocnDetail(), []);
    await ready();
    expect(screen.getByText(/Customer replaces ABC123-RL with ABC123-SH/)).toBeTruthy();
  });

  it('renders no UUID text anywhere', async () => {
    mount(ocnDetail(), [CREATE, EDIT, APPROVE]);
    await ready();
    expect(document.body.textContent).not.toMatch(UUID_RE);
  });
});

describe('G4 the Customer Service comment block', () => {
  it('shows an empty state with a heading and a hint, and no button, until CS has written', async () => {
    mount(ocnDetail({ cs_comment: null }), []);
    await ready();
    expect(screen.getByText('Customer Service comment')).toBeTruthy();
    const empty = screen.getByText('No comment yet');
    const box = empty.parentElement as HTMLElement;
    expect((box.textContent ?? '').trim().length).toBeGreaterThan('No comment yet'.length);
    expect(within(box).queryByRole('button')).toBeNull();
  });

  it('shows the comment, not the empty state, once CS has written it', async () => {
    mount(
      ocnDetail({ status: 'processed_by_cs', approval_status: 'approved', cs_comment: 'Keyed into the SO' }),
      [],
    );
    await ready();
    expect(screen.getByText('Keyed into the SO')).toBeTruthy();
    expect(screen.queryByText('No comment yet')).toBeNull();
  });
});

describe('G4 the sign-off block', () => {
  it('reads Decision, Name, Date and Remarks, Pending until a decision', async () => {
    mount(ocnDetail({ status: 'submitted', approval_status: 'pending' }), []);
    await ready();
    for (const label of ['Decision', 'Name', 'Remarks']) expect(screen.getByText(label)).toBeTruthy();
    expect((screen.getByText('Decision').parentElement?.textContent ?? '')).toMatch(/Pending/);
  });

  it('after approval it names the approver, the day as dd/mm/yyyy and the remarks', async () => {
    mount(
      ocnDetail({
        status: 'approved',
        approval_status: 'approved',
        approver_name: 'Manager A',
        approved_at: '2026-11-09T03:00:00',
        approval_comments: 'Go ahead',
      }),
      [],
    );
    await ready();
    expect(screen.getByText('Manager A')).toBeTruthy();
    expect(screen.getByText('09/11/2026')).toBeTruthy();
    expect(screen.getByText('Go ahead')).toBeTruthy();
    expect((screen.getByText('Decision').parentElement?.textContent ?? '')).toMatch(/Approved/);
  });
});

describe('G4 loading ends in content or an error', () => {
  it('a record that cannot load ends in an error with a way to try again', async () => {
    state.perms = new Set([VIEW]);
    state.get.mockRejectedValue(new Error('Could not load the notice'));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <OrderChangeNoticeDetail ocnId={OCN_ID} />
      </QueryClientProvider>,
    );
    expect(await screen.findByRole('button', { name: /try again|retry/i })).toBeTruthy();
  });
});
