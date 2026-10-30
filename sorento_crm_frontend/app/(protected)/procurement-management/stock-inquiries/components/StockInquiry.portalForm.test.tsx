/**
 * PORTAL-P4-REQUESTS R1 (form parity, owner rule): a LIMITED user (`view_own`, not `view`) creates, edits and VIEWS a
 * Stock Inquiry through the PORTAL's own SubmissionForm, wired to `/api/v1/my-requests` by an injected client.
 * Asserted at the HTTP seam (`apiFetch`) plus the D7 pending-action service. Entry points are the components the
 * pages render: StockInquiryForm (new / edit) and StockInquiryDetail (view). Staff (`view`) keep today's screens.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createCrmApi, SI_DETAIL } from '@/app/(auth)/portal/components/__fixtures__/crmSubmissionApi';

const push = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => '/procurement-management/stock-inquiries/new',
  useSearchParams: () => new URLSearchParams(window.location.search),
}));
vi.mock('next-auth/react', () => ({
  useSession: () => ({ data: { user: { name: 'Ann Sales' } }, status: 'authenticated' }),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn(), dismiss: vi.fn() } }));
vi.mock('@/components/common/deferredToast', () => ({ deferredToast: vi.fn(() => 't'), dismissDeferredToast: vi.fn() }));
vi.mock('@/components/common/AttachmentPreviewModal', () => ({ __esModule: true, default: () => null }));
vi.mock('@/hooks/usePublicViewLinksEnabled', () => ({ usePublicViewLinksEnabled: () => false }));
vi.mock('./StockInquiryAttachmentsSection', () => ({ __esModule: true, default: () => null }));
vi.mock('./StockInquiryNavigation', () => ({ __esModule: true, default: () => null }));
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

const inquiryRef: { current: Record<string, unknown> } = { current: {} };
vi.mock('../hooks/useStockInquiries', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  stockInquiriesPagerQuery: { listQueryKey: () => ['stock-inquiries'], fetchPage: async () => ({ data: [], pagination: { total: 0 } }) },
  useStockInquiry: () => ({ data: inquiryRef.current, isLoading: false }),
  useUpdateStockInquiry: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdateStockInquiryAndReply: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useSubmitStockInquiryForProjectSales: () => ({ mutate: vi.fn(), isPending: false }),
  useProjectSalesApproveStockInquiry: () => ({ mutate: vi.fn(), isPending: false }),
  useProjectSalesRejectStockInquiry: () => ({ mutateAsync: vi.fn(), isPending: false }),
  usePurchasingRejectStockInquiry: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useReopenStockInquiry: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUploadStockInquiryResponseAttachments: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useDeleteStockInquiry: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useExportStockInquiryPdf: () => ({ mutate: vi.fn(), isPending: false }),
  useStockInquiryRevisions: () => ({ data: [], isLoading: false, isError: false }),
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

let detailNow: Record<string, unknown> = SI_DETAIL();
const api = createCrmApi('stock_inquiry', () => detailNow);
vi.mock('@/lib/api', () => ({ apiFetch: (...a: [string, RequestInit?]) => api.handler(...a) }));

import StockInquiryForm from './StockInquiryForm';
import StockInquiryDetail from './StockInquiryDetail';

const LIMITED = ['procurement.stock_inquiries.view_own', 'procurement.stock_inquiries.add'];
const STAFF = [
  'procurement.stock_inquiries.view', 'procurement.stock_inquiries.add', 'procurement.stock_inquiries.edit',
  'procurement.stock_inquiries.delete', 'procurement.stock_inquiries.submit_for_project_sales',
  'procurement.stock_inquiries.project_sales_approve', 'procurement.stock_inquiries.project_sales_reject',
  'procurement.stock_inquiries.purchasing_reject', 'procurement.stock_inquiries.reopen',
  'procurement.stock_inquiries.void', 'sla_management.conversation_sla_tracking.reassign',
];
const calls = api.calls;
const urls = (pred: (c: (typeof calls)[number]) => boolean) => calls.filter(pred);

function wrap(node: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
}
function mountForm(slugs: string[], props: { inquiryId?: string } = {}) {
  held = new Set(slugs);
  return wrap(<StockInquiryForm {...props} />);
}
function mountDetail(slugs: string[], over: Record<string, unknown> = {}) {
  held = new Set(slugs);
  detailNow = SI_DETAIL(over);
  inquiryRef.current = { ...detailNow, inquiry_number: 'SI-2026-0005' };
  return wrap(<StockInquiryDetail inquiryId="si-5" />);
}

beforeEach(() => {
  cleanup();
  calls.length = 0;
  vi.clearAllMocks();
  detailNow = SI_DETAIL();
  pending.getCurrentPendingAction.mockResolvedValue({ pending: null, last_outcome: null });
});

describe('limited user, New Stock Inquiry renders the portal form', () => {
  it('product code is a dropdown searching /api/v1/my-requests/lookups/products', async () => {
    mountForm(LIMITED);
    fireEvent.change(await screen.findByPlaceholderText('Search products...'), { target: { value: 'PR' } });
    await waitFor(() => expect(urls((c) => c.url.startsWith('/api/v1/my-requests/lookups/products')).length).toBeGreaterThan(0), { timeout: 3000 });
  });

  it('project customer is a dropdown searching /api/v1/my-requests/lookups/debtors', async () => {
    mountForm(LIMITED);
    fireEvent.change(await screen.findByPlaceholderText('Search debtors...'), { target: { value: 'De' } });
    await waitFor(() => expect(urls((c) => c.url.startsWith('/api/v1/my-requests/lookups/debtors')).length).toBeGreaterThan(0), { timeout: 3000 });
  });

  it('delivery date is the portal date input, and the profile comes from /api/v1/my-requests/me', async () => {
    mountForm(LIMITED);
    await waitFor(() => expect(document.getElementById('delivery_date')).not.toBeNull());
    expect((document.getElementById('delivery_date') as HTMLInputElement).type).toBe('date');
    await waitFor(() => expect(urls((c) => c.url === '/api/v1/my-requests/me').length).toBeGreaterThan(0));
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
    expect(order.indexOf('POST /api/v1/my-requests/submissions/stock_inquiry')).toBeLessThan(order.indexOf('POST /api/v1/my-requests/attachments'));
  });

  it('Save as draft POSTs and Submit goes to /api/v1/my-requests/submissions/stock_inquiry...', async () => {
    mountForm(LIMITED);
    fireEvent.click(await screen.findByRole('button', { name: 'Save as draft' }));
    await waitFor(() => expect(urls((c) => c.method === 'POST' && c.url === '/api/v1/my-requests/submissions/stock_inquiry')).toHaveLength(1));
    fireEvent.click(await screen.findByRole('button', { name: /^Submit/ }));
    await act(async () => { await new Promise((r) => setTimeout(r, 150)); });
    const dialog = screen.queryByRole('dialog') ?? screen.queryByRole('alertdialog');
    const confirm = dialog && Array.from(dialog.querySelectorAll('button')).find((b) => /submit|confirm|yes|send/i.test(b.textContent ?? ''));
    if (confirm) fireEvent.click(confirm);
    await waitFor(() => expect(urls((c) => c.method === 'POST' && /^\/api\/v1\/my-requests\/submissions\/stock_inquiry\/[^/]+\/submit$/.test(c.url)).length).toBeGreaterThan(0));
    expect(urls((c) => c.url.startsWith('/api/v1/procurement/stock-inquiries') && c.method !== 'GET')).toHaveLength(0);
  });
});

describe('limited user, Stock Inquiry view renders the portal form read-only', () => {
  it('shows the not-editable banner, disabled controls, and Comments + Revisions tabs, loaded from my-requests', async () => {
    mountDetail(LIMITED, { status: 'pending_purchasing', is_draft: false, is_editable: false });
    expect(await screen.findByText('This submission is not editable.')).toBeInTheDocument();
    await waitFor(() => expect(document.getElementById('product_code')).not.toBeNull());
    expect((document.getElementById('product_code') as HTMLInputElement | HTMLTextAreaElement).disabled).toBe(true);
    expect((document.getElementById('delivery_date') as HTMLInputElement).disabled).toBe(true);
    expect(screen.getByRole('tab', { name: /Comments/ })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /Revisions/ })).toBeInTheDocument();
    expect(urls((c) => c.method === 'GET' && c.url === '/api/v1/my-requests/submissions/stock_inquiry/si-5').length).toBeGreaterThan(0);
    expect(urls((c) => c.url.startsWith('/api/v1/procurement/stock-inquiries'))).toHaveLength(0);
  });

  it.each(['Update & Reply', 'Submit for project sales', 'Purchasing Reject', 'Reopen', 'Void', 'Reassign', 'Escalate SLA', 'Extend deadline'])(
    'has no staff action %s even with every staff slug held',
    async (label) => {
      mountDetail([...LIMITED, ...STAFF.filter((s) => !s.endsWith('.view'))], { status: 'pending_purchasing', is_draft: false, is_editable: false });
      await screen.findByText('This submission is not editable.');
      const names = [...screen.queryAllByRole('button'), ...screen.queryAllByRole('menuitem')].map((n) => (n.textContent ?? '').trim());
      expect(names).not.toContain(label);
    },
  );
});

describe('limited user, deletes inside the portal form are D7 deferred (never an immediate DELETE)', () => {
  it('Delete draft parks my_request.delete', async () => {
    pending.createPendingAction.mockResolvedValue({
      id: 'pa-1', action_key: 'my_request.delete', entity_type: 'stock_inquiry', entity_id: 'si-5',
      commit_at: new Date(Date.now() + 10_000).toISOString().replace(/\.\d+Z$/, ''), window_seconds: 10,
    });
    mountForm(LIMITED, { inquiryId: 'si-5' });
    fireEvent.click(await screen.findByRole('button', { name: /Delete draft|Delete/i }));
    await waitFor(() =>
      expect(pending.createPendingAction).toHaveBeenCalledWith(
        expect.objectContaining({ actionKey: 'my_request.delete', entityType: 'stock_inquiry', entityId: 'si-5' }),
      ),
    );
    expect(urls((c) => c.method === 'DELETE')).toHaveLength(0);
  });

  it('removing an own attachment parks my_request_attachment.unlink', async () => {
    detailNow = SI_DETAIL({
      attachments: [{ link_id: 'link-1', attachment_id: 'att-1', filename: 'mine.pdf', size: 3, url: 'https://cdn/mine.pdf', uploader_kind: 'contact', can_unlink: true }],
    });
    pending.createPendingAction.mockResolvedValue({
      id: 'pa-2', action_key: 'my_request_attachment.unlink', entity_type: 'my_request_attachment', entity_id: 'link-1',
      commit_at: new Date(Date.now() + 10_000).toISOString().replace(/\.\d+Z$/, ''), window_seconds: 10,
    });
    mountForm(LIMITED, { inquiryId: 'si-5' });
    fireEvent.click(await screen.findByRole('button', { name: 'Remove attachment' }));
    await waitFor(() =>
      expect(pending.createPendingAction).toHaveBeenCalledWith(
        expect.objectContaining({ actionKey: 'my_request_attachment.unlink', entityType: 'my_request_attachment', entityId: 'link-1' }),
      ),
    );
    expect(urls((c) => c.method === 'DELETE')).toHaveLength(0);
  });
});

describe('staff keep today\'s Stock Inquiry screens', () => {
  it('staff New has no portal form: no draft buttons, no product dropdown, nothing sent to my-requests', async () => {
    mountForm(['procurement.stock_inquiries.view', 'procurement.stock_inquiries.add', 'procurement.stock_inquiries.edit']);
    await screen.findByPlaceholderText('Code');
    expect(screen.queryByRole('button', { name: 'Save as draft' })).toBeNull();
    expect(screen.queryByPlaceholderText('Search products...')).toBeNull();
    expect(urls((c) => c.url.startsWith('/api/v1/my-requests'))).toHaveLength(0);
  });

  it('staff detail still offers its action buttons and is not the portal form', async () => {
    mountDetail(STAFF, { status: 'pending_purchasing', is_draft: false, is_editable: false, response_write_allowed: true, respond_inbox_url: 'https://inbox.example/1', purchasing_response: 'ok' });
    await screen.findAllByText(/SI-2026-0005/);
    expect(screen.queryByText('This submission is not editable.')).toBeNull();
    const gear = screen.queryByRole('button', { name: 'Stock inquiry actions' });
    if (gear) {
      fireEvent.pointerDown(gear, { button: 0, pointerId: 1 });
      fireEvent.pointerUp(gear, { button: 0, pointerId: 1 });
      fireEvent.click(gear);
      await waitFor(() => expect(gear.getAttribute('aria-expanded')).toBe('true'));
    }
    const names = [...screen.queryAllByRole('button'), ...screen.queryAllByRole('menuitem')].map((n) => (n.textContent ?? '').trim());
    for (const want of ['Update & Reply', 'Edit', 'Void', 'Delete', 'Chat records', 'Print / Download PDF', 'Export to Excel', 'Download history'])
      expect(names, `staff lost ${want}`).toContain(want);
    expect(urls((c) => c.url.startsWith('/api/v1/my-requests'))).toHaveLength(0);
  });
});
