/**
 * PORTAL-P4-REQUESTS S3 (P4-25, P4-26): the Purchase Request / Sponsorship Form detail for a LIMITED user shows the
 * portal action set ONLY (Q2 a): Edit (draft/rejected), Delete (draft), Submit (draft/rejected), Revise (server
 * policy allows), Duplicate (always). Every staff action is absent even when its slug is held. Status, the
 * approval / sign-off footer and the Revisions tab stay visible, read-only. Staff detail unchanged.
 * Scaffolding follows PurchaseRequestDetail.test.tsx and StockInquiryDetail.requestScope.test.tsx.
 */
import { submitVerb } from '@/lib/submission-status';
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(''),
}));

const trackersRef = vi.hoisted(() => ({ current: [] as unknown[] }));
vi.mock('@/app/(protected)/sla-management/_shared/formSLAService', () => ({
  getFormSLATrackers: async () => trackersRef.current,
  escalateFormTracking: vi.fn(),
}));
vi.mock('@/app/(protected)/sla-management/_shared/SlaActiveTrackerControls', () => ({ SlaActiveTrackerControls: () => null }));
vi.mock('@/app/(protected)/sla-management/_shared/SlaExtendAction', () => ({
  SlaExtendMenuItem: () => <div role="menuitem">Extend deadline</div>,
  SlaExtendDialog: () => null,
}));
vi.mock('@/app/(protected)/sla-management/_shared/HandlingLockBanner', () => ({ HandlingLockBanner: () => null }));
vi.mock('@/app/(protected)/sla-management/_shared/HandlingLockActions', () => ({ HandlingLockReleaseMenuItem: () => null }));
vi.mock('@/app/(protected)/sla-management/_shared/useFormAction', () => ({
  useFormAction: () => ({ view: { kind: 'idle' }, ctasDisabled: false, cancel: vi.fn(), undo: vi.fn(), refresh: vi.fn(), isMutating: false }),
}));
vi.mock('@/app/(protected)/sla-management/_shared/useHandlingLock', () => ({
  useHandlingLock: () => ({
    state: 'not_escalated', businessCtasEnabled: true, tracker: { id: 't1', is_resolved: false, event_logs: [] },
    claim: vi.fn(), takeOver: vi.fn(), release: vi.fn(), refresh: vi.fn(), isMutating: false,
  }),
}));
vi.mock('@/app/(protected)/sla-management/conversation-sla-tracking/components/ReassignDialog', () => ({ __esModule: true, default: () => null }));
vi.mock('@/app/(protected)/sla-management/conversation-sla-tracking/hooks/useTeamPendingSLA', () => ({
  useReassignSLATracking: () => ({ mutate: vi.fn(), isPending: false }),
}));

let held = new Set<string>();
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => held.has(slug),
  useHasAnyPermission: (slugs: string[]) => slugs.some((s) => held.has(s)),
  usePermissions: () => ({ permissionSet: held, permissions: [...held], isLoading: false, isError: false }),
}));
vi.mock('@/hooks/useFormVoid', () => ({ useFormVoid: () => ({ mutateAsync: vi.fn(), isPending: false }) }));
vi.mock('@/hooks/usePublicViewLinksEnabled', () => ({ usePublicViewLinksEnabled: () => true }));
vi.mock('@/hooks/useLookupOptionsByBinding', () => ({ useLookupOptionsByBinding: () => ({ data: undefined, isLoading: false }) }));
vi.mock('./PurchaseRequestNavigation', () => ({ __esModule: true, default: () => null }));
vi.mock('./PurchaseRequestAttachmentsSection', () => ({ __esModule: true, default: () => null }));
vi.mock('./PurchaseRequestConversationPanel', () => ({ __esModule: true, default: () => null }));
vi.mock('./PurchaseRequestSignoffFooter', () => ({
  PurchaseRequestSignoffFooter: () => <div data-testid="signoff-footer">sign-off</div>,
}));
vi.mock('@/components/audit/AuditTrail', () => ({ __esModule: true, default: () => null }));
vi.mock('@/components/common/ListPager', () => ({ __esModule: true, default: () => null }));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));
vi.mock('../services/purchaseRequestService', () => ({
  sendApprovalLink: vi.fn(),
  setPendingApproval: vi.fn(),
  getUsersForApproverSelect: vi.fn().mockResolvedValue([]),
  getOrCreateViewLink: vi.fn(),
  rejectSubmittedPurchaseRequest: vi.fn(),
  processPurchaseRequestByCs: vi.fn(),
  closePurchaseRequestByCs: vi.fn(),
  submitApprovalDecision: vi.fn(),
  getPurchaseRequestRevisions: vi.fn().mockResolvedValue([]),
  isDeferredDecision: () => false,
}));

const reqRef: { current: Record<string, unknown> } = { current: {} };
vi.mock('../hooks/usePurchaseRequests', () => ({
  purchaseRequestsPagerQuery: { listQueryKey: () => ['purchase-requests'], fetchPage: async () => ({ data: [], pagination: { total: 0 } }) },
  usePurchaseRequest: () => ({ data: reqRef.current, isLoading: false }),
  usePurchaseRequestNeighbours: () => ({ prevId: null, nextId: null, index: null, total: 0, isLoading: false }),
  useDeletePurchaseRequestAttachment: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useDeletePurchaseRequest: () => ({ mutateAsync: vi.fn(), isPending: false }),
  usePurchaseRequestConversation: () => ({ data: undefined, isLoading: false }),
  useExportPurchaseRequestPdf: () => ({ mutate: vi.fn(), isPending: false }),
  usePurchaseRequestRevisions: () => ({ data: [], isLoading: false, isError: false }),
}));

// The revision policy comes from the portal-shaped GET (or from the record itself); both carry the same answer.
const policy = { current: {} as Record<string, unknown> };
vi.mock('@/lib/api', () => ({
  apiFetch: async () =>
    new Response(JSON.stringify({ ...reqRef.current, revision: policy.current, items: [], settings: {} }), {
      status: 200,
      headers: { 'content-type': 'application/json' },
    }),
}));

import PurchaseRequestDetail from './PurchaseRequestDetail';

type Kind = 'purchase_request' | 'sponsorship_form';
const KINDS: Array<{ kind: Kind; base: string; number: string }> = [
  { kind: 'purchase_request', base: 'procurement.purchase_requests', number: 'PR26-0001' },
  { kind: 'sponsorship_form', base: 'procurement.sponsorship_forms', number: 'SF26-0001' },
];
const PORTAL_SET = ['Edit', 'Delete', 'Submit', submitVerb('rejected'), 'Revise', 'Duplicate'];

function record(k: (typeof KINDS)[number], over: Record<string, unknown> = {}) {
  return {
    id: 'pr-1',
    request_type: k.kind,
    request_number: k.number,
    status: 'draft',
    approval_status: null,
    respond_inbox_url: 'https://inbox.example/1',
    updated_at: '2026-07-01T00:00:00Z',
    revision_no: 1,
    sales_type: 'project',
    ...over,
  };
}

function mount(k: (typeof KINDS)[number], slugs: string[], over: Record<string, unknown> = {}, revisable = false) {
  held = new Set(slugs);
  reqRef.current = record(k, over);
  trackersRef.current = [{ id: 'tr-1', is_resolved: false, event_logs: [], team_set_code: 'customer_service' }];
  policy.current = { enabled: true, allowed: revisable, used: 0, max: 3, remaining: 3, blocked_reason: revisable ? null : 'not now' };
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <PurchaseRequestDetail requestId="pr-1" />
    </QueryClientProvider>,
  );
}

/** Every action label on the page: header buttons plus the items of the open gear menu. */
async function actionLabels(k: (typeof KINDS)[number]): Promise<string[]> {
  await screen.findAllByText(new RegExp(k.number));
  const text = (n: Element) => (n.textContent ?? '').trim();
  const collect = () =>
    [...screen.queryAllByRole('button'), ...screen.queryAllByRole('menuitem'), ...screen.queryAllByRole('link')].map(text);
  // Header buttons are read before the gear opens (an open Radix menu aria-hides the rest of the page).
  const before = collect();
  const gear = screen.queryByRole('button', { name: 'Request actions' });
  if (gear) {
    fireEvent.pointerDown(gear, { button: 0, pointerId: 1 });
    fireEvent.pointerUp(gear, { button: 0, pointerId: 1 });
    fireEvent.click(gear);
    await waitFor(() => expect(gear.getAttribute('aria-expanded')).toBe('true'));
  }
  return Array.from(new Set([...before, ...collect()])).filter((t) => t && t !== 'Request actions');
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe.each(KINDS)('$kind detail, limited user', (k) => {
  const LIMITED = [`${k.base}.view_own`, `${k.base}.add`];
  const STAFF_SLUGS = [
    `${k.base}.send_for_approval`, `${k.base}.approve`, `${k.base}.process`, `${k.base}.close`, `${k.base}.void`,
    `${k.base}.edit`, `${k.base}.delete`, 'sla_management.conversation_sla_tracking.reassign',
  ];
  const STAFF = [`${k.base}.view`, ...STAFF_SLUGS];

  it('draft: Edit, Delete, Submit, Duplicate and nothing outside the portal set', async () => {
    mount(k, [...LIMITED, ...STAFF_SLUGS]);
    const labels = await actionLabels(k);
    for (const want of ['Edit', 'Delete', 'Submit', 'Duplicate']) expect(labels, `missing ${want}`).toContain(want);
    expect(labels).not.toContain('Revise');
    expect(labels.filter((l) => !PORTAL_SET.includes(l)), 'non-portal actions leaked').toEqual([]);
  });

  it('rejected: Edit, Submit, Duplicate, no Delete', async () => {
    mount(k, LIMITED, { status: 'submitted', approval_status: 'rejected' });
    const labels = await actionLabels(k);
    expect(labels).toContain('Edit');
    expect(labels).toContain(submitVerb('rejected'));
    expect(labels).toContain('Duplicate');
    expect(labels).not.toContain('Delete');
  });

  it('approved with revision allowed: Revise and Duplicate, no Edit/Delete/Submit', async () => {
    mount(k, LIMITED, { status: 'submitted', approval_status: 'approved' }, true);
    await waitFor(async () => expect(await actionLabels(k)).toContain('Revise'));
    const labels = await actionLabels(k);
    expect(labels).toContain('Duplicate');
    for (const hidden of ['Edit', 'Delete', 'Submit']) expect(labels).not.toContain(hidden);
  });

  it('approved with revision refused by the server: no Revise', async () => {
    mount(k, LIMITED, { status: 'submitted', approval_status: 'approved' }, false);
    expect(await actionLabels(k)).not.toContain('Revise');
  });

  it('pending approval: Duplicate only', async () => {
    mount(k, LIMITED, { status: 'submitted', approval_status: 'pending' });
    const labels = await actionLabels(k);
    expect(labels).toContain('Duplicate');
    expect(labels.filter((l) => !PORTAL_SET.includes(l))).toEqual([]);
    for (const hidden of ['Edit', 'Delete', 'Submit', 'Revise']) expect(labels).not.toContain(hidden);
  });

  it.each([
    'Change to pending approval', 'Reject', 'Approve', 'Processed by CS', 'Mark as closed', 'Void', 'Reassign',
    'Escalate SLA', 'Extend deadline', 'Chat records', 'Print / Download PDF', 'Export to Excel',
    'Copy view link', 'Copy approval link', 'Update & Reply', 'Download history',
  ])('hides %s even with every workflow slug held', async (label) => {
    mount(k, [...LIMITED, ...STAFF_SLUGS], { status: 'submitted', approval_status: 'approved' });
    expect(await actionLabels(k)).not.toContain(label);
  });

  it('still shows the sign-off footer, read-only (the Revisions tab lives in the page wrapper)', async () => {
    mount(k, LIMITED, { status: 'submitted', approval_status: 'approved' });
    await screen.findAllByText(new RegExp(k.number));
    expect(screen.getAllByTestId('signoff-footer').length).toBeGreaterThan(0);
    expect(screen.queryByRole('button', { name: /^(Approve|Reject)$/ })).toBeNull();
  });
});

describe.each(KINDS)('$kind detail, staff user (control, P4-26)', (k) => {
  it('keeps the staff action set', async () => {
    mount(k, [`${k.base}.view`, `${k.base}.edit`, `${k.base}.delete`, `${k.base}.void`], { status: 'draft' });
    const labels = await actionLabels(k);
    for (const want of ['Edit', 'Delete', 'Print / Download PDF', 'Export to Excel', 'Download history', 'Escalate SLA']) {
      expect(labels, `staff lost ${want}`).toContain(want);
    }
    expect(labels).not.toContain('Duplicate');
    expect(labels).not.toContain('Revise');
  });
});
