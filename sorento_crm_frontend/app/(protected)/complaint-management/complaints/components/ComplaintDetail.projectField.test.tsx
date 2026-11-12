/**
 * PROJECT-RELATED-RECORDS fix round 2 (review B1, AC-C6a / D2): the complaint's own page has the
 * shared Registered project field, editable by whoever may edit the complaint, at any status.
 * Scaffolding copied from ComplaintDetail.auditScope.test.tsx.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const push = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(''),
  usePathname: () => '/complaint-management/complaints/cmp-1',
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

import ComplaintDetail from './ComplaintDetail';

const STAFF = ['complaint_management.complaints.view'];
const EDIT = 'complaint_management.complaints.edit';

function mount(slugs: string[]) {
  held = new Set(slugs);
  complaintRef.current = {
    id: 'cmp-1', complaint_number: 'CMP-2026-0001', status: 'closed', complaint_date: '2026-07-01',
    created_at: '2026-07-01T00:00:00Z', attachments: [], revision_no: 0, response_write_allowed: false,
    project_id: 'prj-1', project_code: 'PS26-0001', project_name: 'Zzt Harbour View',
  };
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ComplaintDetail complaintId="cmp-1" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  cleanup();
  slaSpy.mockReset();
  slaSpy.mockImplementation(async () => []);
});

describe('Complaint detail: Registered project (PROJECT-RELATED-RECORDS D2)', () => {
  it('a closed complaint shows its project, and an editor may change it', async () => {
    mount([...STAFF, EDIT]);
    const field = await screen.findByTestId('record-project');
    expect(field.getAttribute('data-kind')).toBe('complaint');
    expect(field.getAttribute('data-label')).toBe('PS26-0001 - Zzt Harbour View');
    expect(field.getAttribute('data-can-edit')).toBe('true');
  });

  it('without the edit right it is read-only', async () => {
    mount(STAFF);
    const field = await screen.findByTestId('record-project');
    expect(field.getAttribute('data-can-edit')).toBe('false');
  });
});
