/**
 * PORTAL-P4-REQUESTS R1 (form parity, owner rule): a LIMITED user (`view_own`, not `view`) creates, edits and VIEWS a
 * Complaint through the PORTAL's own SubmissionForm, wired to `/api/v1/my-requests` by an injected client.
 * Asserted at the HTTP seam (`apiFetch`) plus the D7 pending-action service. Entry points are the components the
 * pages render: ComplaintForm (new / edit) and ComplaintDetail (view). Staff (`view`) keep today's screens.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createCrmApi, CMP_DETAIL } from '@/app/(auth)/portal/components/__fixtures__/crmSubmissionApi';

const push = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => '/complaint-management/complaints/new',
  useSearchParams: () => new URLSearchParams(window.location.search),
}));
vi.mock('next-auth/react', () => ({
  useSession: () => ({ data: { user: { name: 'Ann Sales' } }, status: 'authenticated' }),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn(), dismiss: vi.fn() } }));
vi.mock('@/components/common/deferredToast', () => ({ deferredToast: vi.fn(() => 't'), dismissDeferredToast: vi.fn() }));
vi.mock('@/components/common/AttachmentPreviewModal', () => ({ __esModule: true, default: () => null }));
vi.mock('@/hooks/usePublicViewLinksEnabled', () => ({ usePublicViewLinksEnabled: () => false }));
vi.mock('./ComplaintManualAttachmentsSection', () => ({ __esModule: true, default: () => null }));
vi.mock('./ComplaintConversationPanel', () => ({ __esModule: true, default: () => null }));
vi.mock('@/components/my-downloads/EntityDownloadsButton', () => ({ EntityDownloadsButton: () => null }));
vi.mock('@/app/(protected)/complaint-management/complaint-root-causes/hooks/useComplaintRootCauses', () => ({ useComplaintRootCausesSelect: () => ({ data: [], error: null, refetch: vi.fn() }) }));
vi.mock('@/app/(protected)/complaint-management/complaint-resolutions/hooks/useComplaintResolutions', () => ({ useComplaintResolutionsSelect: () => ({ data: [], error: null, refetch: vi.fn() }) }));
vi.mock('@/components/common/LookupBoundField', () => ({ __esModule: true, default: () => null }));
vi.mock('@/app/(protected)/sla-management/_shared/useFormSkip', () => ({ useFormSkip: () => ({ canSkip: true, actionLabel: 'Settled on site', isSubmitting: false, skip: vi.fn() }) }));
vi.mock('@/components/audit/AuditTrail', () => ({ __esModule: true, default: () => null }));
vi.mock('@/components/common/ListPager', () => ({ __esModule: true, default: () => null }));
vi.mock('@/app/(protected)/sla-management/_shared/formSLAService', () => ({ getFormSLATrackers: async () => [], escalateFormTracking: vi.fn() }));
vi.mock('@/app/(protected)/sla-management/_shared/SlaActiveTrackerControls', () => ({ SlaActiveTrackerControls: () => null }));
vi.mock('@/app/(protected)/sla-management/_shared/SlaExtendAction', () => ({ SlaExtendMenuItem: () => null, SlaExtendDialog: () => null }));
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
vi.mock('@/hooks/useFormVoid', () => ({ useFormVoid: () => ({ mutateAsync: vi.fn(), isPending: false }) }));

const complaintRef: { current: Record<string, unknown> } = { current: {} };
vi.mock('../hooks/useComplaints', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useComplaint: () => ({ data: complaintRef.current, isLoading: false }),
}));

let held = new Set<string>();
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => held.has(slug),
  useHasAnyPermission: (slugs: string[]) => slugs.some((s) => held.has(s)),
  usePermissions: () => ({ permissionSet: held, permissions: [...held], isLoading: false, isError: false }),
}));

const pending = vi.hoisted(() => ({
  createPendingAction: vi.fn(),
  cancelPendingAction: vi.fn(),
  getCurrentPendingAction: vi.fn(),
}));
vi.mock('@/services/pendingActionService', () => pending);

let detailNow: Record<string, unknown> = CMP_DETAIL();
const api = createCrmApi('complaint', () => detailNow);
vi.mock('@/lib/api', () => ({ apiFetch: (...a: [string, RequestInit?]) => api.handler(...a) }));

import ComplaintForm from './ComplaintForm';
import ComplaintDetail from './ComplaintDetail';

const LIMITED = ['complaint_management.complaints.view_own', 'complaint_management.complaints.add'];
const WORKFLOW = [
  'complaint_management.complaints.approve', 'complaint_management.complaints.reject',
  'complaint_management.complaints.resolve', 'complaint_management.complaints.close',
  'complaint_management.complaints.void', 'complaint_management.complaints.settle_on_site',
  'complaint_management.complaints.edit', 'complaint_management.complaints.delete',
  'sla_management.conversation_sla_tracking.reassign',
];
const STAFF = ['complaint_management.complaints.view', 'complaint_management.complaints.add', ...WORKFLOW];
const calls = api.calls;
const urls = (pred: (c: (typeof calls)[number]) => boolean) => calls.filter(pred);

function wrap(node: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
}
function mountForm(slugs: string[], props: { complaintId?: string } = {}) {
  held = new Set(slugs);
  return wrap(<ComplaintForm {...props} />);
}
function mountDetail(slugs: string[], over: Record<string, unknown> = {}) {
  held = new Set(slugs);
  detailNow = CMP_DETAIL(over);
  complaintRef.current = {
    ...detailNow,
    complaint_number: 'CMP-2026-0005',
    technical_team_response: 'ZZT replace the cartridge.',
    root_cause_name: 'ZZT worn seal',
    resolution_name: 'ZZT part replaced',
    respond_inbox_url: 'https://inbox.example/1',
    response_write_allowed: true,
  };
  return wrap(<ComplaintDetail complaintId="cp-5" />);
}

beforeEach(() => {
  cleanup();
  calls.length = 0;
  vi.clearAllMocks();
  detailNow = CMP_DETAIL();
  pending.getCurrentPendingAction.mockResolvedValue({ pending: null, last_outcome: null });
});

describe('limited user, New Complaint renders the portal form', () => {
  it('the DO multi-select loads from /api/v1/my-requests/lookups/delivery-orders', async () => {
    mountForm(LIMITED);
    fireEvent.click(await screen.findByRole('button', { name: /Search delivery orders/i }));
    await waitFor(() => expect(urls((c) => c.url.startsWith('/api/v1/my-requests/lookups/delivery-orders')).length).toBeGreaterThan(0));
  });

  it.each(['complaints_customer_type', 'complaints_within_warranty', 'complaints_defects_discovered', 'complaints_complaint_type'])(
    'lookup set %s comes from /api/v1/my-requests/lookups/sets/...',
    async (key) => {
      mountForm(LIMITED);
      await waitFor(() => expect(urls((c) => c.url === `/api/v1/my-requests/lookups/sets/${key}`).length).toBeGreaterThan(0));
    },
  );

  it('customer is a dropdown on /api/v1/my-requests/lookups/debtors; there is no CRM-only "Customer Type (Other)"', async () => {
    mountForm(LIMITED);
    fireEvent.change(await screen.findByPlaceholderText('Search debtors...'), { target: { value: 'De' } });
    await waitFor(() => expect(urls((c) => c.url.startsWith('/api/v1/my-requests/lookups/debtors')).length).toBeGreaterThan(0), { timeout: 3000 });
    expect(screen.queryByText(/Customer Type \(Other\)/i)).toBeNull();
  });

  it('the product-line dropdown searches /api/v1/my-requests/lookups/products', async () => {
    mountForm(LIMITED);
    fireEvent.click(await screen.findByRole('button', { name: /Add product/i }));
    const code = document.querySelector('[data-field-name="product_lines"] tbody input, [data-field-name="product_lines"] tbody textarea') as HTMLInputElement;
    expect(code).not.toBeNull();
    fireEvent.change(code, { target: { value: 'PR' } });
    await waitFor(() => expect(urls((c) => c.url.startsWith('/api/v1/my-requests/lookups/products')).length).toBeGreaterThan(0), { timeout: 3000 });
  });

  it('defaults the complaint date to today and the salesperson to the signed-in contact (from /me)', async () => {
    mountForm(LIMITED);
    await waitFor(() => expect((document.getElementById('complaint_date') as HTMLInputElement | null)?.value ?? '').toMatch(/^\d{4}-\d{2}-\d{2}$/));
    await waitFor(() => expect((document.getElementById('salesperson') as HTMLInputElement | null)?.value).toBe('Ann Sales'));
    expect(urls((c) => c.url === '/api/v1/my-requests/me').length).toBeGreaterThan(0);
  });

  it('the dropzone is on create and a picked file uploads via /api/v1/my-requests/attachments after the draft exists', async () => {
    const { container } = mountForm(LIMITED);
    expect(await screen.findByRole('button', { name: /Choose file/i })).toBeInTheDocument();
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    await act(async () => {
      fireEvent.change(input, { target: { files: [new File(['abc'], 'f.pdf', { type: 'application/pdf' })] } });
    });
    expect(urls((c) => c.url === '/api/v1/my-requests/attachments')).toHaveLength(0);
    fireEvent.click(await screen.findByRole('button', { name: 'Save as draft' }));
    await waitFor(() => expect(urls((c) => c.url === '/api/v1/my-requests/attachments' && c.method === 'POST')).toHaveLength(1));
  });
});

describe('limited user, Complaint view renders the portal form read-only', () => {
  it('shows the not-editable banner, disabled controls and Comments + Revisions tabs, loaded from my-requests', async () => {
    mountDetail(LIMITED, { status: 'submitted', is_draft: false, is_editable: false });
    expect(await screen.findByText('This submission is not editable.')).toBeInTheDocument();
    await waitFor(() => expect(document.getElementById('contact_person')).not.toBeNull());
    expect((document.getElementById('contact_person') as HTMLInputElement).disabled).toBe(true);
    expect((document.getElementById('complaint_date') as HTMLInputElement).disabled).toBe(true);
    expect(screen.getByRole('tab', { name: /Comments/ })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /Revisions/ })).toBeInTheDocument();
    expect(urls((c) => c.method === 'GET' && c.url === '/api/v1/my-requests/submissions/complaint/cp-5').length).toBeGreaterThan(0);
    expect(urls((c) => c.url.startsWith('/api/v1/complaint-management/complaints'))).toHaveLength(0);
  });

  it.each(['Approve', 'Reject', 'Processed by CS', 'Mark as closed', 'Void', 'Settled on site', 'Reassign', 'Update & Reply', 'Edit root cause', 'Edit resolution', 'Edit technical team response'])(
    'has no staff action %s even with every staff slug held',
    async (label) => {
      mountDetail([...LIMITED, ...WORKFLOW], { status: 'submitted', is_draft: false, is_editable: false });
      await screen.findByText('This submission is not editable.');
      const names = [...screen.queryAllByRole('button'), ...screen.queryAllByRole('menuitem')].map((n) => (n.getAttribute('aria-label') || n.textContent || '').trim());
      expect(names).not.toContain(label);
    },
  );
});

describe('limited user, deletes inside the portal form are D7 deferred (never an immediate DELETE)', () => {
  it('Delete draft parks my_request.delete', async () => {
    pending.createPendingAction.mockResolvedValue({
      id: 'pa-1', action_key: 'my_request.delete', entity_type: 'complaint', entity_id: 'cp-5',
      commit_at: new Date(Date.now() + 10_000).toISOString().replace(/\.\d+Z$/, ''), window_seconds: 10,
    });
    mountForm(LIMITED, { complaintId: 'cp-5' });
    fireEvent.click(await screen.findByRole('button', { name: /Delete draft|Delete/i }));
    await waitFor(() =>
      expect(pending.createPendingAction).toHaveBeenCalledWith(
        expect.objectContaining({ actionKey: 'my_request.delete', entityType: 'complaint', entityId: 'cp-5' }),
      ),
    );
    expect(urls((c) => c.method === 'DELETE')).toHaveLength(0);
  });

  it('removing an own attachment parks my_request_attachment.unlink', async () => {
    detailNow = CMP_DETAIL({
      attachments: [{ link_id: 'link-1', attachment_id: 'att-1', filename: 'mine.pdf', size: 3, url: 'https://cdn/mine.pdf', uploader_kind: 'contact', can_unlink: true }],
    });
    pending.createPendingAction.mockResolvedValue({
      id: 'pa-2', action_key: 'my_request_attachment.unlink', entity_type: 'my_request_attachment', entity_id: 'link-1',
      commit_at: new Date(Date.now() + 10_000).toISOString().replace(/\.\d+Z$/, ''), window_seconds: 10,
    });
    mountForm(LIMITED, { complaintId: 'cp-5' });
    fireEvent.click(await screen.findByRole('button', { name: 'Remove attachment' }));
    await waitFor(() =>
      expect(pending.createPendingAction).toHaveBeenCalledWith(
        expect.objectContaining({ actionKey: 'my_request_attachment.unlink', entityType: 'my_request_attachment', entityId: 'link-1' }),
      ),
    );
    expect(urls((c) => c.method === 'DELETE')).toHaveLength(0);
  });
});

describe('staff keep today\'s Complaint screens', () => {
  it('staff New has the Technical Team card and no portal form', async () => {
    mountForm(['complaint_management.complaints.view', 'complaint_management.complaints.add', 'complaint_management.complaints.edit']);
    expect(await screen.findByText('Technical Team Response')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Save as draft' })).toBeNull();
    expect(screen.queryByPlaceholderText('Search debtors...')).toBeNull();
    expect(urls((c) => c.url.startsWith('/api/v1/my-requests'))).toHaveLength(0);
  });

  it('staff detail keeps every action button, including root cause / resolution / technical response edit', async () => {
    mountDetail(STAFF, { status: 'responded', is_draft: false, is_editable: false });
    await screen.findAllByText(/CMP-2026-0005/);
    expect(screen.queryByText('This submission is not editable.')).toBeNull();
    const gear = screen.queryByRole('button', { name: 'Complaint actions' });
    const before = [...screen.queryAllByRole('button'), ...screen.queryAllByRole('link')].map((n) => (n.getAttribute('aria-label') || n.textContent || '').trim());
    let inMenu: string[] = [];
    if (gear) {
      fireEvent.pointerDown(gear, { button: 0, pointerId: 1 });
      fireEvent.pointerUp(gear, { button: 0, pointerId: 1 });
      fireEvent.click(gear);
      await waitFor(() => expect(gear.getAttribute('aria-expanded')).toBe('true'));
      inMenu = screen.queryAllByRole('menuitem').map((n) => (n.textContent || '').trim());
    }
    const names = [...before, ...inMenu];
    for (const want of ['Edit root cause', 'Edit resolution', 'Edit technical team response', 'Void', 'Update & Reply'])
      expect(names, `staff lost ${want}`).toContain(want);
    expect(urls((c) => c.url.startsWith('/api/v1/my-requests'))).toHaveLength(0);
  });
});
