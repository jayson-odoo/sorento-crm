/**
 * PORTAL-P4-REQUESTS S2 (P4-25, P4-14, P4-26): the Complaint detail for a LIMITED user shows the portal action set
 * ONLY (Q2 a): Edit (draft/rejected), Delete (draft), Submit (draft/rejected), Revise (server policy allows),
 * Duplicate (always). Every staff action (listed in STAFF_ACTIONS) is absent even when its slug is held. Status,
 * root cause, resolution and technical response stay visible, read-only. Staff detail unchanged.
 * Scaffolding follows ComplaintDetail.test.tsx and the S1 StockInquiryDetail.requestScope.test.tsx.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const push = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(''),
}));
vi.mock('@/app/(protected)/sla-management/_shared/formSLAService', () => ({
  getFormSLATrackers: async () => [{ id: 't1', is_resolved: false, event_logs: [] }],
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
vi.mock('@/components/audit/AuditTrail', () => ({ __esModule: true, default: () => null }));
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
const PORTAL_SET = ['Edit', 'Delete', 'Submit', 'Revise', 'Duplicate'];
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
  cleanup();
  vi.clearAllMocks();
  apiCalls.length = 0;
});

describe('limited user, detail', () => {
  it('draft: Edit, Delete, Submit, Duplicate and nothing outside the portal set', async () => {
    mount([...LIMITED, ...WORKFLOW_SLUGS]);
    const labels = await actionLabels();
    for (const want of ['Edit', 'Delete', 'Submit', 'Duplicate']) expect(labels, `missing ${want}`).toContain(want);
    expect(labels).not.toContain('Revise');
    expect(labels.filter((l) => !PORTAL_SET.includes(l)), 'non-portal actions leaked').toEqual([]);
  });

  it('rejected: Edit, Submit, Duplicate, no Delete', async () => {
    mount(LIMITED, { status: 'rejected' });
    const labels = await actionLabels();
    for (const want of ['Edit', 'Submit', 'Duplicate']) expect(labels).toContain(want);
    expect(labels).not.toContain('Delete');
  });

  it('processed with revision allowed: Revise and Duplicate, no Edit/Delete/Submit', async () => {
    mount(LIMITED, { status: 'processed_by_cs' }, true);
    await waitFor(async () => expect(await actionLabels()).toContain('Revise'));
    const labels = await actionLabels();
    expect(labels).toContain('Duplicate');
    for (const hidden of ['Edit', 'Delete', 'Submit']) expect(labels).not.toContain(hidden);
  });

  it('processed with revision refused by the server: no Revise', async () => {
    mount(LIMITED, { status: 'processed_by_cs' }, false);
    expect(await actionLabels()).not.toContain('Revise');
  });

  it('submitted (with the staff slugs held): Duplicate only', async () => {
    mount([...LIMITED, ...WORKFLOW_SLUGS], { status: 'submitted' });
    const labels = await actionLabels();
    expect(labels).toContain('Duplicate');
    expect(labels.filter((l) => !PORTAL_SET.includes(l))).toEqual([]);
    for (const hidden of ['Edit', 'Delete', 'Submit', 'Revise']) expect(labels).not.toContain(hidden);
  });

  it.each(STAFF_ACTIONS)('hides %s even with every workflow slug held', async (label) => {
    // Processed by CS / Mark as closed only show for staff on an approved complaint, the rest on a responded one.
    const status = label === 'Processed by CS' || label === 'Mark as closed' ? 'approved' : 'responded';
    mount([...LIMITED, ...WORKFLOW_SLUGS], { status });
    expect(await actionLabels()).not.toContain(label);
  });

  it('Duplicate goes to /new?from=<id>', async () => {
    mount(LIMITED, { status: 'submitted' });
    await actionLabels();
    fireEvent.click(await screen.findByText('Duplicate'));
    await waitFor(() => expect(push).toHaveBeenCalled());
    expect(String(push.mock.calls[0][0])).toContain('/complaint-management/complaints/new?from=cmp-1');
  });

  it('Revise goes to /<id>/edit?revise=1', async () => {
    mount(LIMITED, { status: 'processed_by_cs' }, true);
    await waitFor(async () => expect(await actionLabels()).toContain('Revise'));
    fireEvent.click(await screen.findByText('Revise'));
    await waitFor(() => expect(push).toHaveBeenCalled());
    expect(String(push.mock.calls[0][0])).toContain('/complaint-management/complaints/cmp-1/edit?revise=1');
  });

  it('Submit on a draft POSTs through my-requests', async () => {
    mount(LIMITED, { status: 'draft' });
    await actionLabels();
    fireEvent.click(await screen.findByText('Submit'));
    await new Promise((r) => setTimeout(r, 150));
    const dialog = screen.queryByRole('dialog') ?? screen.queryByRole('alertdialog');
    const confirm = dialog && Array.from(dialog.querySelectorAll('button')).find((b) => /submit|confirm|yes|send/i.test(b.textContent ?? ''));
    if (confirm) fireEvent.click(confirm);
    await waitFor(() =>
      expect(apiCalls).toContainEqual({ url: '/api/v1/my-requests/submissions/complaint/cmp-1/submit', method: 'POST' }),
    );
  });

  it('still shows status, root cause, resolution and technical response, read-only', async () => {
    mount(LIMITED, { status: 'responded' });
    await screen.findAllByText(/CMP-2026-0001/);
    expect(screen.getAllByText('Responded').length).toBeGreaterThan(0);
    expect(screen.getByText('ZZT worn seal')).toBeInTheDocument();
    expect(screen.getByText('ZZT part replaced')).toBeInTheDocument();
    expect(screen.getByText(/ZZT replace the cartridge\./)).toBeInTheDocument();
    expect(document.querySelector('textarea')).toBeNull();
    expect(screen.queryAllByRole('button', { name: /^Edit (root cause|resolution|technical team response)/ })).toHaveLength(0);
  });
});

describe('staff user, detail (control, P4-26)', () => {
  it('keeps the staff action set', async () => {
    mount(STAFF, { status: 'responded' });
    const labels = await actionLabels();
    for (const want of ['Edit technical team response', 'Approve', 'Reject', 'Void', 'Download PDF', 'Download history', 'Reassign']) {
      expect(labels, `staff lost ${want}`).toContain(want);
    }
    cleanup();
    mount(STAFF, { status: 'approved' });
    const approved = await actionLabels();
    for (const want of ['Processed by CS', 'Mark as closed']) expect(approved, `staff lost ${want}`).toContain(want);
    expect(labels).not.toContain('Duplicate');
    expect(labels).not.toContain('Revise');
    expect(labels).not.toContain('Submit');
  });
});
