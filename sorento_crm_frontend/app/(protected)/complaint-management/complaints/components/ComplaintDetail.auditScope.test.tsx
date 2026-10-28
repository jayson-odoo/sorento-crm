/**
 * PORTAL-P4-REQUESTS S2 (P4-25, P4-14, P4-26): the Complaint detail for a LIMITED user shows the portal action set
 * ONLY (Q2 a): Edit (draft/rejected), Delete (draft), Submit (draft/rejected), Revise (server policy allows),
 * Duplicate (always). Every staff action (listed in STAFF_ACTIONS) is absent even when its slug is held. Status,
 * root cause, resolution and technical response stay visible, read-only. Staff detail unchanged.
 * Scaffolding follows ComplaintDetail.test.tsx and the S1 StockInquiryDetail.requestScope.test.tsx.
 */
import { submitVerb } from '@/lib/submission-status';
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const push = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(''),
}));
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
vi.mock('@/app/(protected)/sla-management/_shared/useFormSkip', () => ({
  useFormSkip: () => ({ canSkip: true, actionLabel: 'Settled on site', isSubmitting: false, skip: vi.fn() }),
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
vi.mock('./ComplaintManualAttachmentsSection', () => ({ __esModule: true, default: () => null }));
vi.mock('./ComplaintConversationPanel', () => ({ __esModule: true, default: () => null }));
vi.mock('@/components/audit/AuditTrail', () => ({ default: () => <div data-testid="audit-trail" /> }));
vi.mock('@/components/common/ListPager', () => ({ __esModule: true, default: () => null }));
vi.mock('@/components/my-downloads/EntityDownloadsButton', () => ({ EntityDownloadsButton: () => null }));
vi.mock('@/app/(protected)/complaint-management/complaint-root-causes/hooks/useComplaintRootCauses', () => ({
  useComplaintRootCausesSelect: () => ({ data: [] }),
}));
vi.mock('@/app/(protected)/complaint-management/complaint-resolutions/hooks/useComplaintResolutions', () => ({
  useComplaintResolutionsSelect: () => ({ data: [] }),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));

const complaintRef: { current: Record<string, unknown> } = { current: {} };
vi.mock('../hooks/useComplaints', () => ({
  complaintsPagerQuery: { listQueryKey: () => ['complaints'], fetchPage: async () => ({ data: [], pagination: { total: 0 } }) },
  useComplaint: () => ({ data: complaintRef.current, isLoading: false }),
  useUpdateComplaint: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdateComplaintAndReply: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useApproveComplaint: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useRejectComplaint: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useProcessComplaintByCs: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useCloseComplaint: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useExportComplaintPdf: () => ({ mutate: vi.fn(), isPending: false }),
  useNotifyComplaintRootCause: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useNotifyComplaintResolution: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUploadComplaintResponseAttachments: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useDeleteComplaint: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

// The revision policy comes from the portal-shaped GET (or from the record itself); both carry the same answer.
const policy = { current: { enabled: true, allowed: false, used: 0, max: 3, remaining: 3, blocked_reason: null } as Record<string, unknown> };
const apiCalls: Array<{ url: string; method: string }> = [];
vi.mock('@/lib/api', () => ({
  apiFetch: async (url: string, init?: RequestInit) => {
    apiCalls.push({ url, method: (init?.method ?? 'GET').toUpperCase() });
    return new Response(JSON.stringify({ ...complaintRef.current, revision: policy.current, items: [] }), {
      status: 200,
      headers: { 'content-type': 'application/json' },
    });
  },
}));

import ComplaintDetail from './ComplaintDetail';

const LIMITED = ['complaint_management.complaints.view_own', 'complaint_management.complaints.add'];
const WORKFLOW_SLUGS = [
  'complaint_management.complaints.approve',
  'complaint_management.complaints.reject',
  'complaint_management.complaints.resolve',
  'complaint_management.complaints.close',
  'complaint_management.complaints.void',
  'complaint_management.complaints.settle_on_site',
  'complaint_management.complaints.edit',
  'complaint_management.complaints.delete',
  'sla_management.conversation_sla_tracking.reassign',
];
const STAFF = ['complaint_management.complaints.view', ...WORKFLOW_SLUGS];
const PORTAL_SET = ['Edit', 'Delete', 'Submit', submitVerb('rejected'), 'Revise', 'Duplicate'];
// Every staff action the detail card offers today (ComplaintDetail.tsx gear menu, header CTAs, inline Edit buttons).
const STAFF_ACTIONS = [
  'Edit technical team response', 'Approve', 'Reject', 'Processed by CS', 'Mark as closed', 'Void',
  'Settled on site', 'Reassign', 'Escalate SLA', 'Extend deadline', 'Edit root cause', 'Edit resolution',
  'Chat records', 'Update & Reply', 'Download PDF', 'Download history', 'Copy view link', 'View in system',
];

function record(over: Record<string, unknown> = {}) {
  return {
    id: 'cmp-1',
    complaint_number: 'CMP-2026-0001',
    status: 'draft',
    complaint_date: '2026-07-01',
    created_at: '2026-07-01T00:00:00Z',
    technical_team_response: 'ZZT replace the cartridge.',
    root_cause_name: 'ZZT worn seal',
    resolution_name: 'ZZT part replaced',
    respond_inbox_url: 'https://inbox.example/1',
    response_write_allowed: true,
    attachments: [],
    revision_no: 0,
    ...over,
  };
}

function mount(slugs: string[], over: Record<string, unknown> = {}, revisable = false) {
  held = new Set(slugs);
  complaintRef.current = record(over);
  policy.current = { enabled: true, allowed: revisable, used: 0, max: 3, remaining: 3, blocked_reason: revisable ? null : 'not now' };
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ComplaintDetail complaintId="cmp-1" />
    </QueryClientProvider>,
  );
}

const nameOf = (n: Element) => (n.getAttribute('aria-label') || n.textContent || '').trim();

/** Every action label on the page: header buttons (read before the menu opens, which aria-hides them) plus the gear menu items. */
async function actionLabels(): Promise<string[]> {
  await screen.findAllByText(/CMP-2026-0001/);
  const visible = () => [...screen.queryAllByRole('button'), ...screen.queryAllByRole('menuitem'), ...screen.queryAllByRole('link')];
  const before = visible().map(nameOf);
  const gear = screen.queryByRole('button', { name: 'Complaint actions' });
  let inMenu: string[] = [];
  if (gear) {
    fireEvent.pointerDown(gear, { button: 0, pointerId: 1 });
    fireEvent.pointerUp(gear, { button: 0, pointerId: 1 });
    fireEvent.click(gear);
    await waitFor(() => expect(gear.getAttribute('aria-expanded')).toBe('true'));
    inMenu = screen.queryAllByRole('menuitem').map(nameOf);
  }
  return [...before, ...inMenu].filter((t) => t && t !== 'Complaint actions');
}

beforeEach(() => {
  slaSpy.mockReset();
  slaSpy.mockImplementation(async () => [{ id: 't1', is_resolved: false, event_logs: [] }]);
  cleanup();
  vi.clearAllMocks();
  apiCalls.length = 0;
});


describe('Audit Trail for a limited user (PORTAL-P4-REQUESTS)', () => {
  it('limited user: no Audit Trail section (the portal has none; /audit/logs answers 403)', async () => {
    mount(LIMITED);
    // R1: their page is the portal's own form, loaded through my-requests.
    await waitFor(() => expect(apiCalls.some((c) => c.url.startsWith('/api/v1/my-requests/submissions/complaint/'))).toBe(true));
    expect(screen.queryByTestId('audit-trail')).toBeNull();
  });

  it('staff: Audit Trail section stays', async () => {
    mount(STAFF);
    await screen.findAllByText(/CMP-2026-0001/);
    expect(await screen.findByTestId('audit-trail')).toBeInTheDocument();
  });
});

describe('SLA by-source read (PORTAL-P4-REQUESTS)', () => {
  it('limited user: getFormSLATrackers (conversation-sla-tracking/by-source) is never called', async () => {
    mount(LIMITED);
    await waitFor(() => expect(apiCalls.some((c) => c.url.startsWith('/api/v1/my-requests/submissions/complaint/'))).toBe(true));
    await new Promise((r) => setTimeout(r, 100));
    expect(slaSpy).not.toHaveBeenCalled();
  });

  it('staff: still reads the trackers', async () => {
    mount(STAFF);
    await screen.findAllByText(/CMP-2026-0001/);
    await waitFor(() => expect(slaSpy).toHaveBeenCalled());
  });
});
