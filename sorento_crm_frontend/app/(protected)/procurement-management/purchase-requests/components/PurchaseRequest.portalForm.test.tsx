/**
 * PORTAL-P4-REQUESTS R2 (form parity, PAR-1/3/5): a LIMITED user (`view_own`, not `view`) creates, edits and VIEWS a
 * Purchase Request through the PORTAL's own SubmissionForm (kind `purchase_request`), wired to `/api/v1/my-requests` by an injected
 * client. Entry points are the components the pages render: PurchaseRequestForm (new / edit) and
 * PurchaseRequestDetail (view). Staff keep today's screens; the staff detail adds "External reference" read-only.
 * Mirrors StockInquiry.portalForm.test.tsx.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createCrmApi, json, PR_DETAIL } from '@/app/(auth)/portal/components/__fixtures__/crmSubmissionApi';

const push = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => '/procurement-management/purchase-requests/new',
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

let detailNow: Record<string, unknown> = PR_DETAIL();
let meNow: Record<string, unknown> = {};
const api = createCrmApi('purchase_request', () => detailNow, () => meNow);
// Staff screens read the staff API; anything under my-requests is answered (and recorded) by the portal fake.
vi.mock('@/lib/api', () => ({
  apiFetch: (...a: [string, RequestInit?]) =>
    a[0].startsWith('/api/v1/my-requests')
      ? api.handler(...a)
      : (api.calls.push({ url: a[0], method: (a[1]?.method ?? 'GET').toUpperCase(), body: null }),
        Promise.resolve(json({ ...requestRef.current, items: [], settings: {}, revision: {} }))),
}));

import PurchaseRequestForm from './PurchaseRequestForm';
import PurchaseRequestDetail from './PurchaseRequestDetail';

const SLUG = 'procurement.purchase_requests';
const LIMITED = [`${SLUG}.view_own`, `${SLUG}.add`];
const STAFF = [`${SLUG}.view`, `${SLUG}.add`, `${SLUG}.edit`, `${SLUG}.delete`];
const calls = api.calls;
const urls = (pred: (c: (typeof calls)[number]) => boolean) => calls.filter(pred);
const BASE = '/procurement-management/purchase-requests';

function wrap(node: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
}
function mountForm(slugs: string[], props: { requestId?: string } = {}) {
  held = new Set(slugs);
  return wrap(<PurchaseRequestForm defaultRequestType="purchase_request" expectedRequestType="purchase_request" {...props} />);
}
function mountDetail(slugs: string[], over: Record<string, unknown> = {}) {
  held = new Set(slugs);
  detailNow = PR_DETAIL(over);
  requestRef.current = {
    id: detailNow.id, request_type: 'purchase_request', request_number: detailNow.reference, status: 'draft',
    customer_name: 'Debtor One', project_title: 'Proj', updated_at: '2026-07-01T00:00:00Z', revision_no: 0,
    sales_type: 'project', respond_inbox_url: 'https://inbox.example/1', ...over,
  };
  return wrap(<PurchaseRequestDetail requestId={String(detailNow.id)} basePath={BASE} />);
}

beforeEach(() => {
  cleanup();
  calls.length = 0;
  vi.clearAllMocks();
  detailNow = PR_DETAIL();
  meNow = {};
  pending.getCurrentPendingAction.mockResolvedValue({ pending: null, last_outcome: null });
});

describe('limited user, New Purchase Request renders the portal form', () => {
  it('is the portal form: no request-type selector, no CRM registered-project picker, Expected PO date is the portal date input', async () => {
    mountForm(LIMITED);
    expect(await screen.findByRole('button', { name: 'Save as draft' })).toBeInTheDocument();
    expect(screen.queryByText('Request type')).toBeNull();
    expect(screen.queryByText('Registered project')).toBeNull();
    await waitFor(() => expect(document.getElementById('expected_delivery_date')).not.toBeNull());
    expect((document.getElementById('expected_delivery_date') as HTMLInputElement).type).toBe('date');
    expect((document.getElementById('expected_po_date') as HTMLInputElement).type).toBe('date');
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
    expect(order.indexOf('POST /api/v1/my-requests/submissions/purchase_request')).toBeLessThan(order.indexOf('POST /api/v1/my-requests/attachments'));
  });

  it('Save as draft POSTs and Submit goes to /api/v1/my-requests/submissions/purchase_request...', async () => {
    mountForm(LIMITED);
    fireEvent.click(await screen.findByRole('button', { name: 'Save as draft' }));
    await waitFor(() => expect(urls((c) => c.method === 'POST' && c.url === '/api/v1/my-requests/submissions/purchase_request')).toHaveLength(1));
    fireEvent.click(await screen.findByRole('button', { name: /^Submit/ }));
    await act(async () => { await new Promise((r) => setTimeout(r, 150)); });
    const dialog = screen.queryByRole('dialog') ?? screen.queryByRole('alertdialog');
    const confirm = dialog && Array.from(dialog.querySelectorAll('button')).find((b) => /submit|confirm|yes|send/i.test(b.textContent ?? ''));
    if (confirm) fireEvent.click(confirm);
    await waitFor(() => expect(urls((c) => c.method === 'POST' && /^\/api\/v1\/my-requests\/submissions\/purchase_request\/[^/]+\/submit$/.test(c.url)).length).toBeGreaterThan(0));
    expect(urls((c) => c.url.startsWith('/api/v1/procurement/purchase-requests') && c.method !== 'GET')).toHaveLength(0);
  });
});



describe('limited user, Purchase Request edit loads from my-requests', () => {
  it('GETs /api/v1/my-requests/submissions/purchase_request/<id> and shows the portal form', async () => {
    mountForm(LIMITED, { requestId: String(PR_DETAIL().id) });
    await waitFor(() => expect(urls((c) => c.method === 'GET' && c.url === '/api/v1/my-requests/submissions/purchase_request/' + String(PR_DETAIL().id)).length).toBeGreaterThan(0));
    expect(await screen.findByRole('button', { name: 'Save as draft' })).toBeInTheDocument();
  });
});

describe('limited user, Purchase Request view renders the portal form read-only', () => {
  it('shows the not-editable banner, disabled controls, and Comments + Revisions tabs, loaded from my-requests', async () => {
    mountDetail(LIMITED, { status: 'pending_approval', is_draft: false, is_editable: false });
    expect(await screen.findByText('This submission is not editable.')).toBeInTheDocument();
    await waitFor(() => expect(document.getElementById('customer_name')).not.toBeNull());
    expect((document.getElementById('customer_name') as HTMLInputElement).disabled).toBe(true);
    expect((document.getElementById('expected_delivery_date') as HTMLInputElement).disabled).toBe(true);
    expect(screen.getByRole('tab', { name: /Comments/ })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /Revisions/ })).toBeInTheDocument();
    expect(urls((c) => c.method === 'GET' && c.url === '/api/v1/my-requests/submissions/purchase_request/' + String(PR_DETAIL().id)).length).toBeGreaterThan(0);
    expect(urls((c) => c.url.startsWith('/api/v1/procurement/purchase-requests'))).toHaveLength(0);
  });
});

describe('limited user, deletes inside the portal form are D7 deferred (never an immediate DELETE)', () => {
  it('Delete draft parks my_request.delete', async () => {
    pending.createPendingAction.mockResolvedValue({
      id: 'pa-1', action_key: 'my_request.delete', entity_type: 'purchase_request', entity_id: String(PR_DETAIL().id),
      commit_at: new Date(Date.now() + 10_000).toISOString().replace(/\.\d+Z$/, ''), window_seconds: 10,
    });
    mountForm(LIMITED, { requestId: String(PR_DETAIL().id) });
    fireEvent.click(await screen.findByRole('button', { name: /Delete draft|Delete/i }));
    await waitFor(() =>
      expect(pending.createPendingAction).toHaveBeenCalledWith(
        expect.objectContaining({ actionKey: 'my_request.delete', entityType: 'purchase_request', entityId: String(PR_DETAIL().id) }),
      ),
    );
    expect(urls((c) => c.method === 'DELETE')).toHaveLength(0);
  });

  it('removing an own attachment parks my_request_attachment.unlink', async () => {
    detailNow = PR_DETAIL({
      attachments: [{ link_id: 'link-1', attachment_id: 'att-1', filename: 'mine.pdf', size: 3, url: 'https://cdn/mine.pdf', uploader_kind: 'contact', can_unlink: true }],
    });
    pending.createPendingAction.mockResolvedValue({
      id: 'pa-2', action_key: 'my_request_attachment.unlink', entity_type: 'my_request_attachment', entity_id: 'link-1',
      commit_at: new Date(Date.now() + 5_000).toISOString().replace(/\.\d+Z$/, ''), window_seconds: 5,
    });
    mountForm(LIMITED, { requestId: String(PR_DETAIL().id) });
    fireEvent.click(await screen.findByRole('button', { name: 'Remove attachment' }));
    await waitFor(() =>
      expect(pending.createPendingAction).toHaveBeenCalledWith(
        expect.objectContaining({ actionKey: 'my_request_attachment.unlink', entityType: 'my_request_attachment', entityId: 'link-1' }),
      ),
    );
    expect(urls((c) => c.method === 'DELETE')).toHaveLength(0);
  });
});

describe('staff keep today\'s Purchase Request screens', () => {
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
