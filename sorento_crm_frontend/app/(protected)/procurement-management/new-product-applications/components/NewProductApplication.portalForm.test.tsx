/**
 * PORTAL-P4-REQUESTS R3a (form parity, PAR-1/3/5): a LIMITED user (`view_own`, holding none of `view` / `approve` /
 * `open_code`) creates, edits and VIEWS a New Product Application through the PORTAL's own NewProductApplicationForm
 * (app/(auth)/portal/components), wired to `/api/v1/my-requests` by an injected client. Entry points are the components
 * the pages render: NewProductApplicationForm (new with ?stock_inquiry_id= / edit) and NewProductApplicationDetail
 * (view). Staff keep today's screens.
 *
 * Marker that tells the PORTAL form from the CRM one on create: the stock inquiry control is the combobox labelled
 * "Start from my stock inquiry" (the CRM has a "Stock inquiry" select). On edit / view the markers are behavioural:
 * the record is read from my-requests and the staff NPA API is never called.
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { EMPTY_FORM, blankLine, payloadFromState } from '@/lib/new-product-application-form';

class ResizeObserverStub { observe() {} unobserve() {} disconnect() {} }
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
Element.prototype.scrollIntoView = vi.fn();

const nav = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn() }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: nav.push, replace: nav.replace, back: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => '/procurement-management/new-product-applications/new',
  useSearchParams: () => new URLSearchParams(''),
}));
vi.mock('next-auth/react', () => ({
  useSession: () => ({ data: { user: { name: 'Ann Sales' } }, status: 'authenticated' }),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn(), dismiss: vi.fn() } }));
vi.mock('@/components/common/deferredToast', () => ({ deferredToast: vi.fn(() => 't'), dismissDeferredToast: vi.fn() }));
vi.mock('@/components/audit/AuditTrail', () => ({ __esModule: true, default: () => null }));
vi.mock('@/components/common/AttachmentPreviewModal', () => ({ __esModule: true, default: () => null }));
vi.mock('@/hooks/usePublicViewLinksEnabled', () => ({ usePublicViewLinksEnabled: () => false }));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
vi.mock('@/hooks/useEffectiveUserId', () => ({ useEffectiveUserId: () => 'u-owner' }));
vi.mock('@/hooks/useDeferredRowAction', () => ({
  useDeferredRowAction: () => ({ run: vi.fn(), targetId: null, isPending: false, countdown: null }),
}));
vi.mock('@/app/(protected)/master-data-management/shared/hooks/use-brand-select-query', () => ({ useBrandSelectQuery: () => ({ data: [] }) }));
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
vi.mock('@/components/ui/dropdown-menu', () => ({
  DropdownMenuItem: ({ children, onSelect }: { children: React.ReactNode; onSelect?: () => void }) => (
    <button onClick={() => onSelect?.()}>{children}</button>
  ),
}));

let held = new Set<string>();
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => held.has(slug),
  useHasAnyPermission: (slugs: string[]) => slugs.some((s) => held.has(s)),
  usePermissions: () => ({ permissionSet: held, permissions: [...held], isLoading: false, isError: false }),
}));

const pending = vi.hoisted(() => ({ createPendingAction: vi.fn(), cancelPendingAction: vi.fn(), getCurrentPendingAction: vi.fn() }));
vi.mock('@/services/pendingActionService', () => pending);

interface Call { url: string; method: string; body: unknown }
const calls: Call[] = [];
const MINE = '/api/v1/my-requests/submissions/new_product_application';
const OWN = '/api/v1/my-requests/new-product-application';
const STAFF_BASE = '/api/v1/procurement/new-product-applications';
const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status, headers: { 'content-type': 'application/json' } });
const line = (over: Record<string, unknown> = {}) => ({
  id: 'l-1', line_no: 1, proposed_code: 'ZZT-1', description: 'Sink', dimension: null, material: null, thickness: null, packing: null,
  brand_id: null, brand_name: null, expected_qty: '5', cost_price: null, opened_product_id: null, opened_product_code: null,
  opened_product_name: null, opened_product_active: null, closed_reason: null, ...over,
});
const detail = (over: Record<string, unknown> = {}) => ({
  id: 'npa-5', application_no: 'NPA-000005', status: 'draft', status_label: 'Draft', source: 'portal',
  applicant_id: 'u-owner', applicant_name: 'Ann Sales', stock_inquiry_id: null, stock_inquiry_number: null,
  customer_id: null, customer_code: null, customer_name: 'ZZT Typed Co', project_name: 'ZZT project', needed_by: null,
  remark: null, lead_time: null, attachments: [], created_at: '2026-10-10T01:00:00', submitted_at: null,
  first_line: 'ZZT-1', lines_total: 1, lines_done: 0, opened_codes: [], decided_at: null, reject_reason: null,
  revise_reason: null, cancel_reason: null, lines: [line()], ...over,
});
const PREFILL = {
  stock_inquiry_id: 'si-1', stock_inquiry_number: 'SI26-0412', customer_id: null, customer_name: 'ZZT DEVELOPER',
  project_name: 'ZZT RESIDENCE', needed_by: null, remark: null,
  lines: [{ proposed_code: 'ZZT-1234', description: 'ZZT sinks', expected_qty: '55' }],
};
let detailNow: Record<string, unknown> = detail();
vi.mock('@/lib/api', () => ({
  apiFetch: async (url: string, init?: RequestInit) => {
    const method = (init?.method ?? 'GET').toUpperCase();
    let body: unknown = init?.body;
    if (typeof body === 'string') {
      try { body = JSON.parse(body); } catch { /* keep */ }
    }
    if (typeof FormData !== 'undefined' && body instanceof FormData) body = Object.fromEntries(body.entries());
    calls.push({ url, method, body });
    const path = url.split('?')[0];
    if (path === '/api/v1/my-requests/attachments' && method === 'POST')
      return json({ link_id: 'ln-1', attachment_id: 'at-1', filename: 'f.pdf', size: 3, url: 'https://cdn/f.pdf', uploader_kind: 'contact', can_unlink: true });
    if (path === `${OWN}/prefill`) return json(PREFILL);
    if (path === `${OWN}/inquiries`)
      return json([{ id: 'si-1', inquiry_number: 'SI26-0412', product_code: 'ZZT-1', item_description: 'd', project_name: 'ZZT RESIDENCE', purchasing_response: 'ok', last_responded_at: null }]);
    if (path === `${OWN}/customers`) return json([{ customer_id: 'd1', customer_code: 'D-1', debtor_name: 'ZZT Debtor' }]);
    if (path.startsWith(`${OWN}/lookups/`)) return json([{ id: 'b1', code: 'B1', name: 'ZZT Brand' }]);
    if (path === MINE && method === 'POST') return json({ ...detailNow, id: 'new-1', lines: [line({ id: 'l-new' })] });
    if (path.endsWith('/submit') && path.startsWith(MINE)) return json({ ...detailNow, status: 'submitted', status_label: 'Submitted' });
    if (path.endsWith('/cancel') && path.startsWith(MINE)) return json({ ...detailNow, status: 'cancelled', status_label: 'Cancelled' });
    if (path === STAFF_BASE && method === 'POST') return json({ ...detailNow, id: 'new-1' });
    if (path.includes('stock-inquiries')) return json({ data: [] });
    return json(detailNow);
  },
}));

import NewProductApplicationForm from './NewProductApplicationForm';
import NewProductApplicationDetail from './NewProductApplicationDetail';

const P = 'procurement.new_product_applications';
const LIMITED = [`${P}.view_own`, `${P}.create`];
const STAFF_VIEW = [`${P}.view`, `${P}.create`];
const STAFF_APPROVER = [`${P}.view_own`, `${P}.approve`];
const where = (pred: (c: Call) => boolean) => calls.filter(pred);
const portalCalls = () => where((c) => c.url.startsWith('/api/v1/public/portal'));
const staffApi = () => where((c) => c.url.startsWith(STAFF_BASE));

function wrap(node: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
}
function mountForm(slugs: string[], props: { applicationId?: string; stockInquiryId?: string } = {}) {
  held = new Set(slugs);
  return wrap(<NewProductApplicationForm {...props} />);
}
function mountDetail(slugs: string[], over: Record<string, unknown> = {}) {
  held = new Set(slugs);
  detailNow = detail(over);
  return wrap(<NewProductApplicationDetail applicationId="npa-5" />);
}
const pickInquiryLabel = 'Start from my stock inquiry';

beforeEach(() => {
  cleanup();
  calls.length = 0;
  vi.clearAllMocks();
  detailNow = detail();
  pending.getCurrentPendingAction.mockResolvedValue({ pending: null, last_outcome: null });
});

describe('limited user, New Product Application create renders the portal form', () => {
  it('is the portal form: the "Start from my stock inquiry" combobox', async () => {
    mountForm(LIMITED);
    expect(await screen.findByLabelText(pickInquiryLabel)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save as draft' })).toBeInTheDocument();
  });

  it('inquiries, customers and brands are searched on my-requests only', async () => {
    mountForm(LIMITED);
    const inquiry = await screen.findByLabelText(pickInquiryLabel);
    fireEvent.focus(inquiry);
    fireEvent.change(inquiry, { target: { value: 'SI' } });
    await waitFor(() => expect(where((c) => c.url.startsWith(`${OWN}/inquiries`)).length).toBeGreaterThan(0), { timeout: 3000 });
    const customer = screen.getByLabelText('Customer');
    fireEvent.focus(customer);
    fireEvent.change(customer, { target: { value: 'ZZ' } });
    await waitFor(() => expect(where((c) => c.url.startsWith(`${OWN}/customers`)).length).toBeGreaterThan(0), { timeout: 3000 });
    fireEvent.click(screen.getByLabelText('Brand'));
    await waitFor(() => expect(where((c) => c.url.startsWith(`${OWN}/lookups/brands`)).length).toBeGreaterThan(0), { timeout: 3000 });
    expect(portalCalls()).toHaveLength(0);
    expect(staffApi()).toHaveLength(0);
    expect(where((c) => c.url.startsWith('/api/v1/procurement/stock-inquiries'))).toHaveLength(0);
  });

  it('Save as draft POSTs the portal payload, then router.replace goes to the CRM detail (never /portal)', async () => {
    mountForm(LIMITED);
    fireEvent.click(await screen.findByRole('button', { name: 'Save as draft' }));
    await waitFor(() => expect(where((c) => c.method === 'POST' && c.url === MINE)).toHaveLength(1));
    expect(where((c) => c.method === 'POST' && c.url === MINE)[0].body).toEqual(payloadFromState({ ...EMPTY_FORM, lines: [blankLine()] }));
    await waitFor(() => expect(nav.replace).toHaveBeenCalledWith('/procurement-management/new-product-applications/new-1'));
    expect(nav.replace.mock.calls.every((a) => !String(a[0]).startsWith('/portal'))).toBe(true);
    expect(staffApi()).toHaveLength(0);
  });

  it('a picked file uploads to /api/v1/my-requests/attachments only after the draft exists', async () => {
    const { container } = mountForm(LIMITED);
    await screen.findByLabelText(pickInquiryLabel);
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    await act(async () => {
      fireEvent.change(input, { target: { files: [new File(['abc'], 'f.pdf', { type: 'application/pdf' })] } });
    });
    expect(where((c) => c.url === '/api/v1/my-requests/attachments')).toHaveLength(0);
    fireEvent.click(await screen.findByRole('button', { name: 'Save as draft' }));
    await waitFor(() => expect(where((c) => c.url === '/api/v1/my-requests/attachments' && c.method === 'POST')).toHaveLength(1));
    const up = where((c) => c.url === '/api/v1/my-requests/attachments')[0].body as Record<string, unknown>;
    expect(up.kind).toBe('new_product_application');
    expect(up.submission_id).toBe('new-1');
    const order = calls.map((c) => `${c.method} ${c.url}`);
    expect(order.indexOf(`POST ${MINE}`)).toBeLessThan(order.indexOf('POST /api/v1/my-requests/attachments'));
    expect(portalCalls()).toHaveLength(0);
  });

  it('Submit saves, POSTs .../<id>/submit, then pushes the CRM list', async () => {
    mountForm(LIMITED);
    fireEvent.click(await screen.findByRole('button', { name: /^Submit$/ }));
    await waitFor(() => expect(where((c) => c.method === 'POST' && c.url === `${MINE}/new-1/submit`)).toHaveLength(1));
    await waitFor(() => expect(nav.push).toHaveBeenCalledWith('/procurement-management/new-product-applications'));
    expect(nav.push.mock.calls.every((a) => !String(a[0]).startsWith('/portal'))).toBe(true);
    expect(staffApi()).toHaveLength(0);
  });

  it('?stock_inquiry_id= starts the portal form from that inquiry (prefill on my-requests) and the save carries it', async () => {
    mountForm(LIMITED, { stockInquiryId: 'si-1' });
    await waitFor(() => expect(where((c) => c.method === 'GET' && c.url === `${OWN}/prefill?stock_inquiry_id=si-1`).length).toBeGreaterThan(0));
    expect(await screen.findByLabelText(pickInquiryLabel)).toBeInTheDocument();
    await waitFor(() => expect((screen.getByLabelText('Customer') as HTMLInputElement).value).toBe('ZZT DEVELOPER'));
    fireEvent.click(screen.getByRole('button', { name: 'Save as draft' }));
    await waitFor(() => expect(where((c) => c.method === 'POST' && c.url === MINE)).toHaveLength(1));
    expect((where((c) => c.method === 'POST' && c.url === MINE)[0].body as { stock_inquiry_id?: string }).stock_inquiry_id).toBe('si-1');
    expect(staffApi()).toHaveLength(0);
    expect(where((c) => c.url.startsWith('/api/v1/procurement/stock-inquiries'))).toHaveLength(0);
  });
});

describe('limited user, New Product Application edit loads from my-requests', () => {
  it('GETs my-requests/submissions/new_product_application/<id>, saves with PUT, never the staff API', async () => {
    mountForm(LIMITED, { applicationId: 'npa-5' });
    fireEvent.click(await screen.findByRole('button', { name: 'Save as draft' }));
    await waitFor(() => expect(where((c) => c.method === 'PUT' && c.url === `${MINE}/npa-5`)).toHaveLength(1));
    expect(where((c) => c.method === 'GET' && c.url === `${MINE}/npa-5`).length).toBeGreaterThan(0);
    expect(screen.queryByLabelText(pickInquiryLabel)).toBeNull();
    expect(staffApi()).toHaveLength(0);
    expect(portalCalls()).toHaveLength(0);
  });

  it('removing an own uploaded attachment parks my_request_attachment.unlink (D7), no immediate DELETE', async () => {
    detailNow = detail({
      attachments: [{ link_id: 'link-1', attachment_id: 'att-1', filename: 'mine.pdf', size: 3, url: 'https://cdn/mine.pdf', uploader_kind: 'contact', can_unlink: true }],
    });
    pending.createPendingAction.mockResolvedValue({
      id: 'pa-2', action_key: 'my_request_attachment.unlink', entity_type: 'my_request_attachment', entity_id: 'link-1',
      commit_at: new Date(Date.now() + 5_000).toISOString().replace(/\.\d+Z$/, ''), window_seconds: 5,
    });
    held = new Set(LIMITED);
    wrap(<NewProductApplicationForm applicationId="npa-5" />);
    fireEvent.click(await screen.findByRole('button', { name: 'Remove attachment' }));
    await waitFor(() =>
      expect(pending.createPendingAction).toHaveBeenCalledWith(
        expect.objectContaining({ actionKey: 'my_request_attachment.unlink', entityType: 'my_request_attachment', entityId: 'link-1' }),
      ),
    );
    expect(where((c) => c.method === 'DELETE')).toHaveLength(0);
  });
});

describe('limited user, New Product Application view renders the portal form read-only', () => {
  it('a submitted application is read from my-requests, shows the portal lock sentence, never the staff API', async () => {
    mountDetail(LIMITED, { status: 'submitted', status_label: 'Submitted' });
    expect(await screen.findByText(/Locked: Revise to change it/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Save as draft' })).toBeNull();
    expect(where((c) => c.method === 'GET' && c.url === `${MINE}/npa-5`).length).toBeGreaterThan(0);
    expect(staffApi()).toHaveLength(0);
    expect(portalCalls()).toHaveLength(0);
  });

  it('Cancel application with a reason POSTs my-requests/.../<id>/cancel', async () => {
    mountDetail(LIMITED, { status: 'submitted', status_label: 'Submitted' });
    fireEvent.click(await screen.findByText('Cancel application'));
    const dialog = await screen.findByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel application' }));
    await waitFor(() => expect(where((c) => c.method === 'POST' && c.url === `${MINE}/npa-5/cancel`)).toHaveLength(1));
    expect(staffApi().filter((c) => c.method !== 'GET')).toHaveLength(0);
  });
});

describe('staff keep today\'s New Product Application screens', () => {
  it('a `.view` holder\'s New is the staff form: no portal combobox, staff create route, nothing on my-requests', async () => {
    mountForm(STAFF_VIEW);
    fireEvent.click(await screen.findByRole('button', { name: 'Save as draft' }));
    await waitFor(() => expect(where((c) => c.method === 'POST' && c.url === STAFF_BASE)).toHaveLength(1));
    expect(screen.queryByLabelText(pickInquiryLabel)).toBeNull();
    expect(where((c) => c.url.startsWith('/api/v1/my-requests'))).toHaveLength(0);
  });

  it('an `.approve` holder (view_own too) is not limited: staff detail from the staff GET', async () => {
    mountDetail(STAFF_APPROVER, { status: 'submitted', status_label: 'Submitted' });
    await screen.findByRole('heading', { name: /NPA-000005/ });
    expect(where((c) => c.method === 'GET' && c.url === `${STAFF_BASE}/npa-5`).length).toBeGreaterThan(0);
    expect(where((c) => c.url.startsWith(`${MINE}/npa-5`) && c.method === 'GET')).toHaveLength(0);
  });

  it('a `.view` holder\'s detail is the staff detail', async () => {
    mountDetail(STAFF_VIEW);
    await screen.findByRole('heading', { name: /NPA-000005/ });
    expect(where((c) => c.url.startsWith('/api/v1/my-requests/submissions'))).toHaveLength(0);
  });
});
