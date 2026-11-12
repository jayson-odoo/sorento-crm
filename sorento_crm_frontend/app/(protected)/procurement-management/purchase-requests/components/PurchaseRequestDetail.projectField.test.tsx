/**
 * PROJECT-RELATED-RECORDS fix round 2 (review B1, AC-C6a / D2): the purchase request and the
 * sponsorship form have the shared Registered project field, editable by whoever may edit that
 * kind, at any status. Scaffolding copied from PurchaseRequestDetail.auditScope.test.tsx.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(''),
}));

const trackersRef = vi.hoisted(() => ({ current: [] as unknown[] }));
const slaSpy = vi.hoisted(() => vi.fn());
vi.mock('@/app/(protected)/sla-management/_shared/formSLAService', () => ({
  getFormSLATrackers: (...a: unknown[]) => slaSpy(...a),
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
vi.mock('@/components/audit/AuditTrail', () => ({ default: () => <div data-testid="audit-trail" /> }));
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

// PROJECT-RELATED-RECORDS fix round 2 (review B1): the detail page passes the shared Project field
// its record, kind and edit right; the field itself is tested on its own.
vi.mock('@/components/common/RecordProjectField', () => ({
  RecordProjectField: (p: { kind: string; canEdit: boolean; projectCode?: string | null; projectTitle?: string | null }) => (
    <div
      data-testid="record-project"
      data-kind={p.kind}
      data-can-edit={String(p.canEdit)}
      data-label={[p.projectCode, p.projectTitle].filter(Boolean).join(' - ')}
    />
  ),
}));

import PurchaseRequestDetail from './PurchaseRequestDetail';

const KINDS = [
  { kind: 'purchase_request', base: 'procurement.purchase_requests', number: 'PR26-0001' },
  { kind: 'sponsorship_form', base: 'procurement.sponsorship_forms', number: 'SF26-0001' },
] as const;

function mount(k: (typeof KINDS)[number], slugs: string[]) {
  held = new Set(slugs);
  reqRef.current = {
    id: 'pr-1', request_type: k.kind, request_number: k.number, status: 'processed_by_cs',
    approval_status: 'approved', updated_at: '2026-07-01T00:00:00Z', revision_no: 0, sales_type: 'project',
    project_title: 'typed tower', project_id: 'prj-1', project_code: 'PS26-0001', project_name: 'Zzt Harbour View',
  };
  policy.current = { enabled: true, allowed: false, used: 0, max: 3, remaining: 3, blocked_reason: 'not now' };
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <PurchaseRequestDetail requestId="pr-1" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  cleanup();
  slaSpy.mockReset();
  slaSpy.mockImplementation(async () => trackersRef.current);
});

describe.each(KINDS)('$kind detail: Registered project (PROJECT-RELATED-RECORDS D2)', (k) => {
  it('an approved record shows its project, and an editor of this kind may change it', async () => {
    mount(k, [`${k.base}.view`, `${k.base}.edit`]);
    const field = await screen.findByTestId('record-project');
    expect(field.getAttribute('data-kind')).toBe(k.kind);
    expect(field.getAttribute('data-label')).toBe('PS26-0001 - Zzt Harbour View');
    expect(field.getAttribute('data-can-edit')).toBe('true');
  });

  it("the other kind's edit right does not count", async () => {
    const other = KINDS.find((x) => x.kind !== k.kind)!;
    mount(k, [`${k.base}.view`, `${other.base}.edit`]);
    const field = await screen.findByTestId('record-project');
    expect(field.getAttribute('data-can-edit')).toBe('false');
  });
});
