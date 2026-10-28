/**
 * PORTAL-P4-REQUESTS R2 (form parity, PAR-1/3/5): a LIMITED user (`view_own`, not `view`) creates, edits and VIEWS a
 * Sponsorship Form through the PORTAL's own SubmissionForm (kind `sponsorship_form`), wired to `/api/v1/my-requests` by an injected
 * client. Entry points are the components the pages render: PurchaseRequestForm (new / edit) and
 * PurchaseRequestDetail (view). Staff keep today's screens; the staff detail adds "External reference" read-only.
 * Mirrors StockInquiry.portalForm.test.tsx.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createCrmApi, json, SF_DETAIL } from '@/app/(auth)/portal/components/__fixtures__/crmSubmissionApi';

const push = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => '/procurement-management/sponsorship-forms/new',
  useSearchParams: () => new URLSearchParams(window.location.search),
}));
vi.mock('next-auth/react', () => ({
  useSession: () => ({ data: { user: { name: 'Ann Sales' } }, status: 'authenticated' }),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn(), dismiss: vi.fn() } }));
vi.mock('@/components/common/deferredToast', () => ({ deferredToast: vi.fn(() => 't'), dismissDeferredToast: vi.fn() }));
vi.mock('@/components/common/AttachmentPreviewModal', () => ({ __esModule: true, default: () => null }));
vi.mock('@/hooks/usePublicViewLinksEnabled', () => ({ usePublicViewLinksEnabled: () => false }));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
vi.mock('./PurchaseRequestAttachmentsSection', () => ({ __esModule: true, default: () => null }));
vi.mock('./PurchaseRequestNavigation', () => ({ __esModule: true, default: () => null }));
vi.mock('./PurchaseRequestConversationPanel', () => ({ __esModule: true, default: () => null }));
vi.mock('./PurchaseRequestSignoffFooter', () => ({ PurchaseRequestSignoffFooter: () => null }));
vi.mock('@/components/audit/AuditTrail', () => ({ __esModule: true, default: () => null }));
vi.mock('@/components/common/ListPager', () => ({ __esModule: true, default: () => null }));
vi.mock('@/components/common/LookupBoundField', () => ({ __esModule: true, default: () => null }));
vi.mock('@/hooks/useLookupOptionsByBinding', () => ({ useLookupOptionsByBinding: () => ({ data: undefined, isLoading: false }) }));
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
vi.mock('@/app/(protected)/project-sales/_shared/services/projectService', () => ({ getProject: vi.fn() }));
vi.mock('@/app/(protected)/master-data-management/shared/components/RequestorContactSelect', () => ({ RequestorContactSelect: () => null }));

const requestRef: { current: Record<string, unknown> } = { current: {} };
vi.mock('../hooks/usePurchaseRequests', () => ({
  purchaseRequestsPagerQuery: { listQueryKey: () => ['purchase-requests'], fetchPage: async () => ({ data: [], pagination: { total: 0 } }) },
  usePurchaseRequest: () => ({ data: requestRef.current, isLoading: false }),
  usePurchaseRequestNeighbours: () => ({ prevId: null, nextId: null, index: null, total: 0, isLoading: false }),
  usePurchaseRequestConversation: () => ({ data: undefined, isLoading: false }),
  usePurchaseRequestRevisions: () => ({ data: [], isLoading: false, isError: false }),
  useCreatePurchaseRequest: () => ({ mutateAsync: vi.fn().mockResolvedValue({ id: 'new-1' }), isPending: false }),
  useUpdatePurchaseRequest: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdatePurchaseRequestAndReply: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useDeletePurchaseRequest: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useDeletePurchaseRequestAttachment: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useExportPurchaseRequestPdf: () => ({ mutate: vi.fn(), isPending: false }),
}));
vi.mock('../services/purchaseRequestService', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  searchProjectsForLink: vi.fn().mockResolvedValue([]),
  getOrCreateViewLink: vi.fn(),
  getUsersForApproverSelect: vi.fn().mockResolvedValue([]),
  getPurchaseRequestRevisions: vi.fn().mockResolvedValue([]),
  isDeferredDecision: () => false,
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

let detailNow: Record<string, unknown> = SF_DETAIL();
let meNow: Record<string, unknown> = {};
const api = createCrmApi('sponsorship_form', () => detailNow, () => meNow);
// Staff screens read the staff API; anything under my-requests is answered (and recorded) by the portal fake.
// R2 project seed: a server refusal (422 code + message) for the next save / submit POST.
let refusal: { on: 'save' | 'submit'; code: string; message: string } | null = null;
vi.mock('@/lib/api', () => ({
  apiFetch: (...a: [string, RequestInit?]) =>
    a[0].startsWith('/api/v1/my-requests')
      ? refusal &&
        (a[1]?.method ?? 'GET').toUpperCase() === 'POST' &&
        (refusal.on === 'submit' ? /\/submit$/.test(a[0]) : a[0] === '/api/v1/my-requests/submissions/sponsorship_form')
        ? (api.calls.push({ url: a[0], method: 'POST', body: a[1]?.body ?? null }),
          Promise.resolve(json({ message: refusal.message, code: refusal.code }, 422)))
        : api.handler(...a)
      : (api.calls.push({ url: a[0], method: (a[1]?.method ?? 'GET').toUpperCase(), body: null }),
        Promise.resolve(json({ ...requestRef.current, items: [], settings: {}, revision: {} }))),
}));

import PurchaseRequestForm from './PurchaseRequestForm';
import PurchaseRequestDetail from './PurchaseRequestDetail';
import { getProject } from '@/app/(protected)/project-sales/_shared/services/projectService';

const SLUG = 'procurement.sponsorship_forms';
const LIMITED = [`${SLUG}.view_own`, `${SLUG}.add`];
const STAFF = [`${SLUG}.view`, `${SLUG}.add`, `${SLUG}.edit`, `${SLUG}.delete`];
const calls = api.calls;
const urls = (pred: (c: (typeof calls)[number]) => boolean) => calls.filter(pred);
const BASE = '/procurement-management/sponsorship-forms';

function wrap(node: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
}
function mountForm(slugs: string[], props: { requestId?: string } = {}) {
  held = new Set(slugs);
  return wrap(<PurchaseRequestForm defaultRequestType="sponsorship_form" expectedRequestType="sponsorship_form" {...props} />);
}
function mountDetail(slugs: string[], over: Record<string, unknown> = {}) {
  held = new Set(slugs);
  detailNow = SF_DETAIL(over);
  requestRef.current = {
    id: detailNow.id, request_type: 'sponsorship_form', request_number: detailNow.reference, status: 'draft',
    customer_name: 'Debtor One', project_title: 'Proj', updated_at: '2026-07-01T00:00:00Z', revision_no: 0,
    sales_type: 'project', respond_inbox_url: 'https://inbox.example/1', ...over,
  };
  return wrap(<PurchaseRequestDetail requestId={String(detailNow.id)} basePath={BASE} />);
}

beforeEach(() => {
  cleanup();
  calls.length = 0;
  vi.clearAllMocks();
  detailNow = SF_DETAIL();
  meNow = {};
  refusal = null;
  pending.getCurrentPendingAction.mockResolvedValue({ pending: null, last_outcome: null });
});

describe('limited user, New Sponsorship Form renders the portal form', () => {
  it('is the portal form: no request-type selector, no CRM registered-project picker, Expected PO date is the portal date input', async () => {
    mountForm(LIMITED);
    expect(await screen.findByRole('button', { name: 'Save as draft' })).toBeInTheDocument();
    expect(screen.queryByText('Request type')).toBeNull();
    
    await waitFor(() => expect(document.getElementById('expected_delivery_date')).not.toBeNull());
    expect((document.getElementById('expected_delivery_date') as HTMLInputElement).type).toBe('date');
    
    await waitFor(() => expect(urls((c) => c.url === '/api/v1/my-requests/me').length).toBeGreaterThan(0));
  });

  it('customer is a dropdown searching /api/v1/my-requests/lookups/debtors', async () => {
    mountForm(LIMITED);
    fireEvent.change(await screen.findByPlaceholderText('Search debtors...'), { target: { value: 'De' } });
    await waitFor(() => expect(urls((c) => c.url.startsWith('/api/v1/my-requests/lookups/debtors')).length).toBeGreaterThan(0), { timeout: 3000 });
  });

  it('a product line item code searches /api/v1/my-requests/lookups/products', async () => {
    mountForm(LIMITED);
    fireEvent.click(await screen.findByRole('button', { name: /Add item/i }));
    const input = screen.getByRole('table').querySelector('input') as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'PR' } });
    await waitFor(() => expect(urls((c) => c.url.startsWith('/api/v1/my-requests/lookups/products')).length).toBeGreaterThan(0), { timeout: 3000 });
  });

  it('sales type options come from /api/v1/my-requests/lookups/sets/procurement_sales_type', async () => {
    mountForm(LIMITED);
    await waitFor(() => expect(urls((c) => c.url === '/api/v1/my-requests/lookups/sets/procurement_sales_type').length).toBeGreaterThan(0));
  });

  it('Requested by defaults to their own contact and its options come from /api/v1/my-requests/requestor-options', async () => {
    mountForm(LIMITED);
    await waitFor(() => expect(document.getElementById('requested_by_contact_id')).not.toBeNull());
    await waitFor(() => expect(screen.getAllByText(/Ann Sales/).length).toBeGreaterThan(0));
    fireEvent.click(document.getElementById('requested_by_contact_id') as HTMLElement);
    await waitFor(() => expect(urls((c) => c.url.startsWith('/api/v1/my-requests/requestor-options')).length).toBeGreaterThan(0), { timeout: 3000 });
  });

  it('has an External reference input', async () => {
    mountForm(LIMITED);
    await waitFor(() => expect(document.getElementById('external_reference')).not.toBeNull());
  });

  it('the attachment dropzone is on create; a picked file uploads via /api/v1/my-requests/attachments only after the draft exists', async () => {
    const { container } = mountForm(LIMITED);
    expect(await screen.findByRole('button', { name: /Choose file/i })).toBeInTheDocument();
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    await act(async () => {
      fireEvent.change(input, { target: { files: [new File(['abc'], 'f.pdf', { type: 'application/pdf' })] } });
    });
    expect(urls((c) => c.url === '/api/v1/my-requests/attachments')).toHaveLength(0);
    fireEvent.click(await screen.findByRole('button', { name: 'Save as draft' }));
    await waitFor(() => expect(urls((c) => c.url === '/api/v1/my-requests/attachments' && c.method === 'POST')).toHaveLength(1));
    const order = calls.map((c) => `${c.method} ${c.url}`);
    expect(order.indexOf('POST /api/v1/my-requests/submissions/sponsorship_form')).toBeLessThan(order.indexOf('POST /api/v1/my-requests/attachments'));
  });

  it('Save as draft POSTs and Submit goes to /api/v1/my-requests/submissions/sponsorship_form...', async () => {
    mountForm(LIMITED);
    fireEvent.click(await screen.findByRole('button', { name: 'Save as draft' }));
    await waitFor(() => expect(urls((c) => c.method === 'POST' && c.url === '/api/v1/my-requests/submissions/sponsorship_form')).toHaveLength(1));
    fireEvent.click(await screen.findByRole('button', { name: /^Submit/ }));
    await act(async () => { await new Promise((r) => setTimeout(r, 150)); });
    const dialog = screen.queryByRole('dialog') ?? screen.queryByRole('alertdialog');
    const confirm = dialog && Array.from(dialog.querySelectorAll('button')).find((b) => /submit|confirm|yes|send/i.test(b.textContent ?? ''));
    if (confirm) fireEvent.click(confirm);
    await waitFor(() => expect(urls((c) => c.method === 'POST' && /^\/api\/v1\/my-requests\/submissions\/sponsorship_form\/[^/]+\/submit$/.test(c.url)).length).toBeGreaterThan(0));
    expect(urls((c) => c.url.startsWith('/api/v1/procurement/purchase-requests') && c.method !== 'GET')).toHaveLength(0);
  });
});

describe('limited user, Sponsorship Form specifics', () => {
  it('has Delivery address, Total project value and Sponsor subject from /lookups/sets/procurement_sponsor_subject', async () => {
    mountForm(LIMITED);
    await waitFor(() => expect(document.getElementById('delivery_address')).not.toBeNull());
    expect(document.getElementById('total_project_value')).not.toBeNull();
    await waitFor(() => expect(urls((c) => c.url === '/api/v1/my-requests/lookups/sets/procurement_sponsor_subject').length).toBeGreaterThan(0));
  });

  it('"Please specify" shows only when Sponsor subject is others', async () => {
    detailNow = SF_DETAIL({ sponsor_subject: 'others', sponsor_subject_other: 'Thing' });
    mountForm(LIMITED, { requestId: 'sf-5' });
    expect(await screen.findByText('Please specify')).toBeInTheDocument();
    cleanup();
    detailNow = SF_DETAIL({ sponsor_subject: 'opt-a' });
    mountForm(LIMITED, { requestId: 'sf-5' });
    await screen.findByRole('button', { name: 'Save as draft' });
    expect(screen.queryByText('Please specify')).toBeNull();
  });

  it('Registered project picker is NOT shown for an unflagged contact', async () => {
    meNow = { requires_registered_project: false };
    mountForm(LIMITED);
    await screen.findByRole('button', { name: 'Save as draft' });
    await waitFor(() => expect(urls((c) => c.url === '/api/v1/my-requests/me').length).toBeGreaterThan(0));
    expect(screen.queryByText('Registered project')).toBeNull();
  });

  it('Registered project is shown and required for a requires_registered_project contact, searching /lookups/projects', async () => {
    meNow = { requires_registered_project: true };
    mountForm(LIMITED);
    expect(await screen.findByText('Registered project')).toBeInTheDocument();
    fireEvent.change(await screen.findByPlaceholderText('Search your registered projects...'), { target: { value: 'PR' } });
    await waitFor(() => expect(urls((c) => c.url.startsWith('/api/v1/my-requests/lookups/projects')).length).toBeGreaterThan(0), { timeout: 3000 });
    fireEvent.click(await screen.findByRole('button', { name: 'Save as draft' }));
    fireEvent.click(await screen.findByRole('button', { name: /^Submit/ }));
    await act(async () => { await new Promise((r) => setTimeout(r, 150)); });
    expect(urls((c) => c.method === 'POST' && /\/submit$/.test(c.url))).toHaveLength(0);
  });
});


describe('limited user, Sponsorship Form edit loads from my-requests', () => {
  it('GETs /api/v1/my-requests/submissions/sponsorship_form/<id> and shows the portal form', async () => {
    mountForm(LIMITED, { requestId: String(SF_DETAIL().id) });
    await waitFor(() => expect(urls((c) => c.method === 'GET' && c.url === '/api/v1/my-requests/submissions/sponsorship_form/' + String(SF_DETAIL().id)).length).toBeGreaterThan(0));
    expect(await screen.findByRole('button', { name: 'Save as draft' })).toBeInTheDocument();
  });
});

describe('limited user, Sponsorship Form view renders the portal form read-only', () => {
  it('shows the not-editable banner, disabled controls, and Comments + Revisions tabs, loaded from my-requests', async () => {
    mountDetail(LIMITED, { status: 'pending_approval', is_draft: false, is_editable: false });
    expect(await screen.findByText('This submission is not editable.')).toBeInTheDocument();
    await waitFor(() => expect(document.getElementById('customer_name')).not.toBeNull());
    expect((document.getElementById('customer_name') as HTMLInputElement).disabled).toBe(true);
    expect((document.getElementById('expected_delivery_date') as HTMLInputElement).disabled).toBe(true);
    expect(screen.getByRole('tab', { name: /Comments/ })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /Revisions/ })).toBeInTheDocument();
    expect(urls((c) => c.method === 'GET' && c.url === '/api/v1/my-requests/submissions/sponsorship_form/' + String(SF_DETAIL().id)).length).toBeGreaterThan(0);
    expect(urls((c) => c.url.startsWith('/api/v1/procurement/purchase-requests'))).toHaveLength(0);
  });
});

describe('limited user, deletes inside the portal form are D7 deferred (never an immediate DELETE)', () => {
  it('Delete draft parks my_request.delete', async () => {
    pending.createPendingAction.mockResolvedValue({
      id: 'pa-1', action_key: 'my_request.delete', entity_type: 'sponsorship_form', entity_id: String(SF_DETAIL().id),
      commit_at: new Date(Date.now() + 10_000).toISOString().replace(/\.\d+Z$/, ''), window_seconds: 10,
    });
    mountForm(LIMITED, { requestId: String(SF_DETAIL().id) });
    fireEvent.click(await screen.findByRole('button', { name: /Delete draft|Delete/i }));
    await waitFor(() =>
      expect(pending.createPendingAction).toHaveBeenCalledWith(
        expect.objectContaining({ actionKey: 'my_request.delete', entityType: 'sponsorship_form', entityId: String(SF_DETAIL().id) }),
      ),
    );
    expect(urls((c) => c.method === 'DELETE')).toHaveLength(0);
  });

  it('removing an own attachment parks my_request_attachment.unlink', async () => {
    detailNow = SF_DETAIL({
      attachments: [{ link_id: 'link-1', attachment_id: 'att-1', filename: 'mine.pdf', size: 3, url: 'https://cdn/mine.pdf', uploader_kind: 'contact', can_unlink: true }],
    });
    pending.createPendingAction.mockResolvedValue({
      id: 'pa-2', action_key: 'my_request_attachment.unlink', entity_type: 'my_request_attachment', entity_id: 'link-1',
      commit_at: new Date(Date.now() + 5_000).toISOString().replace(/\.\d+Z$/, ''), window_seconds: 5,
    });
    mountForm(LIMITED, { requestId: String(SF_DETAIL().id) });
    fireEvent.click(await screen.findByRole('button', { name: 'Remove attachment' }));
    await waitFor(() =>
      expect(pending.createPendingAction).toHaveBeenCalledWith(
        expect.objectContaining({ actionKey: 'my_request_attachment.unlink', entityType: 'my_request_attachment', entityId: 'link-1' }),
      ),
    );
    expect(urls((c) => c.method === 'DELETE')).toHaveLength(0);
  });
});

describe('staff keep today\'s Sponsorship Form screens', () => {
  it('staff New has no portal form: no draft buttons, nothing sent to my-requests', async () => {
    mountForm(STAFF);
    await waitFor(() => expect(document.body.textContent).toMatch(/Customer/));
    expect(screen.queryByRole('button', { name: 'Save as draft' })).toBeNull();
    expect(screen.queryByPlaceholderText('Search debtors...')).toBeNull();
    expect(urls((c) => c.url.startsWith('/api/v1/my-requests'))).toHaveLength(0);
  });

  it('staff detail is not the portal form and keeps its action buttons', async () => {
    mountDetail(STAFF, { status: 'draft' });
    await screen.findAllByText(new RegExp(String(detailNow.reference)));
    expect(screen.queryByText('This submission is not editable.')).toBeNull();
    expect(screen.queryByRole('tab', { name: /Comments/ })).toBeNull();
    const names = [...screen.queryAllByRole('button'), ...screen.queryAllByRole('link')].map((n) => (n.textContent ?? '').trim());
    expect(names).toContain('Edit');
    expect(urls((c) => c.url.startsWith('/api/v1/my-requests/submissions'))).toHaveLength(0);
  });

  it('staff detail shows External reference read-only (text, no input)', async () => {
    mountDetail(STAFF, { external_reference: 'EXT-9' });
    const label = await screen.findByText('External reference');
    expect(within(label.parentElement as HTMLElement).getByText('EXT-9')).toBeInTheDocument();
    expect(document.getElementById('external_reference')).toBeNull();
    expect(screen.queryByDisplayValue('EXT-9')).toBeNull();
  });

  it('an empty External reference renders the detail\'s usual empty marker', async () => {
    mountDetail(STAFF, { external_reference: null });
    const label = await screen.findByText('External reference');
    expect((label.parentElement?.textContent ?? '').replace('External reference', '').trim()).toBe('-');
  });
});

// ---- R2 follow-up: ?project_id= on the salesperson path (owner ruling (a)) ----
const PROJECT_ID = '5b0c1d2e-aaaa-4bbb-8ccc-0123456789ab';
const PROJECT = { id: PROJECT_ID, project_code: 'PRJ-0001', title: 'Project One', company_name: 'Company A' };
const NO_COMPANY = 'Your contact is not linked to any company yet, so no project can be attached. Ask the Sorento team to link your company first.';
const NOT_PERMITTED = 'That project is not one of yours. Pick a project from the list, which shows the ones registered under your company.';

function mountSeeded(defaultProjectId?: string) {
  held = new Set(LIMITED);
  (getProject as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(PROJECT);
  return wrap(<PurchaseRequestForm defaultRequestType="sponsorship_form" defaultProjectId={defaultProjectId} />);
}
const draftFields = () => {
  const post = calls.find((c) => c.method === 'POST' && c.url === '/api/v1/my-requests/submissions/sponsorship_form');
  return ((post?.body ?? {}) as { fields?: Record<string, unknown> }).fields ?? {};
};

describe('limited user, Sponsorship Form seeded from a project (?project_id=)', () => {
  it('unflagged contact: picker hidden, the draft carries project_id and the project title, Project title input shows it', async () => {
    meNow = { requires_registered_project: false };
    mountSeeded(PROJECT_ID);
    await waitFor(() => expect((document.getElementById('project_title') as HTMLInputElement | null)?.value).toBe('Project One'));
    expect(screen.queryByText('Registered project')).toBeNull();
    fireEvent.click(await screen.findByRole('button', { name: 'Save as draft' }));
    await waitFor(() => expect(draftFields().project_id).toBe(PROJECT_ID));
    expect(draftFields().project_title).toBe('Project One');
  });

  it('flagged contact: the picker shows the project by its code (never the UUID) and the draft carries the id', async () => {
    meNow = { requires_registered_project: true };
    mountSeeded(PROJECT_ID);
    expect(await screen.findByText('Registered project')).toBeInTheDocument();
    await waitFor(() => expect((document.getElementById('project_id') as HTMLInputElement | null)?.value ?? '').toContain('PRJ-0001'));
    expect(document.body.textContent).not.toContain(PROJECT_ID);
    fireEvent.click(await screen.findByRole('button', { name: 'Save as draft' }));
    await waitFor(() => expect(draftFields().project_id).toBe(PROJECT_ID));
  });

  it('no defaultProjectId: nothing is seeded and the draft has no project_id', async () => {
    meNow = { requires_registered_project: false };
    mountSeeded(undefined);
    fireEvent.click(await screen.findByRole('button', { name: 'Save as draft' }));
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.url === '/api/v1/my-requests/submissions/sponsorship_form')).toBe(true));
    expect(draftFields().project_id ?? null).toBeNull();
    expect(getProject).not.toHaveBeenCalled();
    expect((document.getElementById('project_title') as HTMLInputElement).value).toBe('');
  });

  it.each([
    ['sponsorship_contact_no_company', NO_COMPANY],
    ['sponsorship_project_not_permitted', NOT_PERMITTED],
  ])('Save as draft refused with %s: a clear alert in the form, no raw code, no navigation', async (code, message) => {
    meNow = { requires_registered_project: false };
    refusal = { on: 'save', code, message };
    mountSeeded(PROJECT_ID);
    fireEvent.click(await screen.findByRole('button', { name: 'Save as draft' }));
    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain(message);
    expect(document.body.textContent).not.toContain(code);
    expect(push).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Save as draft' })).toBeInTheDocument();
  });

  it.each([
    ['sponsorship_contact_no_company', NO_COMPANY],
    ['sponsorship_project_not_permitted', NOT_PERMITTED],
  ])('Submit refused with %s: a clear alert in the form, no raw code, no navigation', async (code, message) => {
    meNow = { requires_registered_project: false };
    refusal = { on: 'submit', code, message };
    mountSeeded(PROJECT_ID);
    fireEvent.click(await screen.findByRole('button', { name: 'Save as draft' }));
    fireEvent.click(await screen.findByRole('button', { name: /^Submit/ }));
    await act(async () => { await new Promise((r) => setTimeout(r, 150)); });
    const dialog = screen.queryByRole('dialog') ?? screen.queryByRole('alertdialog');
    const confirm = dialog && Array.from(dialog.querySelectorAll('button')).find((b) => /submit|confirm|yes|send/i.test(b.textContent ?? ''));
    if (confirm) fireEvent.click(confirm);
    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain(message);
    expect(document.body.textContent).not.toContain(code);
    expect(push).not.toHaveBeenCalled();
  });
});
