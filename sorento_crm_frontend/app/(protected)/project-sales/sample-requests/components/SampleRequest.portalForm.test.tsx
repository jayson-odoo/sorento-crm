/**
 * SAMPLE-REQUEST-V2 slice 2 (owner Q1 a, 11 Nov), which replaced PORTAL-P4-REQUESTS R3a's portal form: a LIMITED
 * user (`view_own`, not `view`) now gets the SAME guided staff form as everyone else (four sections, Save as draft,
 * Preview, Submit inside the Preview popup), but every server call of THEIR form goes through My Requests
 * (`/api/v1/my-requests/...`), never the staff sample request API. Their read-only VIEW is still the portal's
 * SampleRequestDetail. Entry points are the components the pages render: SampleRequestForm (new with ?project_id= /
 * edit), and SampleRequestDetailTabs + SampleRequestDetail (view). Staff keep today's screens.
 *
 * Marker that tells the guided form from the old portal one: the four section titles and the Preview button
 * (the portal form had "Submit sample request" and an "Items" card with "Add item").
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const nav = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn(), search: '' }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: nav.push, replace: nav.replace, back: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => '/project-sales/sample-requests/new',
  useSearchParams: () => new URLSearchParams(nav.search),
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
vi.mock('@/hooks/useDeferredAction', () => ({ useDeferredAction: () => ({ countdown: null, isBlocked: false, start: vi.fn() }) }));
vi.mock('@/app/(protected)/project-sales/_shared/components/OrderInquiryStockGrid', () => ({ OrderInquiryStockGrid: () => null }));
vi.mock('@/app/(protected)/sla-management/_shared/formSLAService', () => ({ getFormSLATrackers: async () => [], escalateFormTracking: vi.fn() }));
vi.mock('@/app/(protected)/sla-management/_shared/FormSLATrackingTab', () => ({ __esModule: true, default: () => null }));
vi.mock('@/components/common/comments/FormComments', () => ({ FormComments: () => null }));
vi.mock('@/hooks/useFormComments', () => ({ useFormCommentsQuery: () => ({ data: [] }) }));
vi.mock('@/components/common/DetailActionsMenu', () => ({
  DetailActionsMenu: ({ children, ariaLabel }: { children: React.ReactNode; ariaLabel?: string }) => (
    <div aria-label={ariaLabel}>{children}</div>
  ),
}));
vi.mock('@/components/ui/dropdown-menu', () => ({
  DropdownMenuItem: ({ children, onSelect }: { children: React.ReactNode; onSelect?: () => void }) => (
    <button onClick={() => onSelect?.()}>{children}</button>
  ),
}));
vi.mock('@/app/(protected)/project-sales/_shared/services/projectService', () => ({
  getProject: vi.fn(),
  // SAMPLE-REQUEST-V2: the staff form's Ship to picker reads the roles and the parties.
  listPartyRoles: vi.fn(async () => []),
  getPartiesOnProject: vi.fn(async () => []),
  listParties: vi.fn(async () => ({ data: [] })),
  listPartyContacts: vi.fn(async () => []),
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
const MINE = '/api/v1/my-requests/submissions/sample_request';
const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status, headers: { 'content-type': 'application/json' } });
const detail = (over: Record<string, unknown> = {}) => ({
  id: 'sr-5', request_no: 'SR-000005', status: 'draft', status_label: 'Draft', source: 'portal',
  salesperson_id: 'u-owner', salesperson_name: 'Ann Sales', customer_id: null, customer_name: 'ZZT Typed Co',
  project_id: null, project_title: 'ZZT project', delivery_date: '2026-12-01', delivery_mode: 'driver', ship_to_name: 'ZZT Site',
  created_at: '2026-10-10T01:00:00',
  lines: [{ id: 'l-1', line_no: 1, product_id: 'p-1', product_code: 'TILE-1', product_name: 'Tile', brand_name: 'B', product_active: true, qty: 2, remark: null }],
  ...over,
});
let detailNow: Record<string, unknown> = detail();
let refusal: { status: number; body: unknown } | null = null;
vi.mock('@/lib/api', () => ({
  apiFetch: async (url: string, init?: RequestInit) => {
    const method = (init?.method ?? 'GET').toUpperCase();
    let body: unknown = init?.body;
    if (typeof body === 'string') {
      try { body = JSON.parse(body); } catch { /* keep */ }
    }
    calls.push({ url, method, body });
    const path = url.split('?')[0];
    if (refusal && method === 'POST' && path === MINE) return json(refusal.body, refusal.status);
    if (path.startsWith('/api/v1/my-requests/sample-request/customers')) return json([{ customer_id: 'd1', customer_code: 'D-1', debtor_name: 'ZZT Debtor' }]);
    if (path.startsWith('/api/v1/my-requests/sample-request/products')) return json([{ id: 'p-1', product_code: 'TILE-1', product_name: 'Tile', brand_name: 'B' }]);
    if (path === '/api/v1/my-requests/lookups/projects') return json([{ id: 'prj-1', project_code: 'PRJ-0001', title: 'Project One', company_name: 'Company A' }]);
    if (path.endsWith('/submit') && path.startsWith(MINE)) return json({ ...detailNow, status: 'submitted', status_label: 'Submitted' });
    if (path.endsWith('/cancel') && path.startsWith(MINE)) return json({ ...detailNow, status: 'cancelled', status_label: 'Cancelled' });
    if (path === MINE && method === 'POST') return json({ ...detailNow, id: 'new-1' });
    if (path.startsWith(`${MINE}/`)) return json(detailNow);
    return json(detailNow);
  },
}));

import SampleRequestForm from './SampleRequestForm';
import SampleRequestDetail from './SampleRequestDetail';
import SampleRequestDetailTabs from './SampleRequestDetailTabs';
import { toast } from '@/lib/toast';
import { getProject } from '@/app/(protected)/project-sales/_shared/services/projectService';

const LIMITED = ['projects.sample_requests.view_own', 'projects.sample_requests.create'];
const STAFF = ['projects.sample_requests.view', 'projects.sample_requests.create', 'projects.sample_requests.process'];
const where = (pred: (c: Call) => boolean) => calls.filter(pred);
const portalCalls = () => where((c) => c.url.startsWith('/api/v1/public/portal'));
const staffApi = () => where((c) => c.url.startsWith('/api/v1/project-sales/sample-requests'));

function wrap(node: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
}
function mountForm(slugs: string[], props: { requestId?: string; projectId?: string } = {}) {
  held = new Set(slugs);
  return wrap(<SampleRequestForm {...props} />);
}
function mountDetail(slugs: string[], over: Record<string, unknown> = {}) {
  held = new Set(slugs);
  detailNow = detail(over);
  return wrap(
    <SampleRequestDetailTabs id="sr-5">
      <SampleRequestDetail requestId="sr-5" />
    </SampleRequestDetailTabs>,
  );
}

beforeEach(() => {
  cleanup();
  calls.length = 0;
  vi.clearAllMocks();
  detailNow = detail();
  refusal = null;
  nav.search = '';
  pending.getCurrentPendingAction.mockResolvedValue({ pending: null, last_outcome: null });
});

const SECTIONS = ['Customer & project', 'Ship to', 'Items', 'Delivery'];
const draftBtn = () => screen.getByRole('button', { name: 'Save as draft' });
const posts = () => where((c) => c.method === 'POST' && c.url === MINE);
/** A draft that passes every staff rule, as My Requests returns it. */
const READY = {
  customer_id: 'd1', customer_name: 'ZZT Debtor', ship_to_party_id: 'party-1', ship_to_role: null,
  ship_to_name: 'ZZT Site', ship_to_address: '1 Jalan Test, Klang', delivery_date: '2026-11-18', delivery_mode: 'driver',
  loan_value: 2, loan_unit: 'months', goods_from: 'either', board_mounting: false,
};

describe('limited user, New Sample Request renders the guided form through My Requests', () => {
  it('is the guided form (four sections, Save as draft, Preview), not the portal one, and not the staff API', async () => {
    mountForm(LIMITED);
    for (const t of SECTIONS) expect((await screen.findAllByText(t, { selector: 'span' })).length).toBeGreaterThan(0);
    expect(screen.getByRole('button', { name: 'Save as draft' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Preview' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Submit sample request' })).toBeNull();
    expect(screen.queryByRole('button', { name: /Add item/ })).toBeNull();
    // Submit lives inside the Preview popup only.
    expect(screen.queryByRole('button', { name: /^Submit$/ })).toBeNull();
    expect(staffApi()).toHaveLength(0);
  });

  it('customer and product search go to my-requests, projects to the own-scope CRM search', async () => {
    mountForm(LIMITED);
    await screen.findByText('Customer & project');
    const customer = screen.getByLabelText(/^Customer/);
    fireEvent.focus(customer);
    fireEvent.change(customer, { target: { value: 'ZZ' } });
    await waitFor(() => expect(where((c) => c.url.startsWith('/api/v1/my-requests/sample-request/customers')).length).toBeGreaterThan(0), { timeout: 3000 });
    fireEvent.change(screen.getByRole('combobox', { name: /item code/i }), { target: { value: 'TI' } });
    await waitFor(() => expect(where((c) => c.url.startsWith('/api/v1/my-requests/sample-request/products')).length).toBeGreaterThan(0), { timeout: 3000 });
    fireEvent.click(document.getElementById('sr-project') as HTMLElement);
    const box = await screen.findByPlaceholderText('Search...');
    fireEvent.change(box, { target: { value: 'PR' } });
    // Projects: the CRM project search, which the own-scope guard answers with this salesperson's own
    // projects only (the company-wide portal lookup is refused on save; security review B1, slice 2).
    await waitFor(() => expect(where((c) => c.url.startsWith('/api/v1/project-sales/projects/')).length).toBeGreaterThan(0), { timeout: 3000 });
    expect(where((c) => c.url.startsWith('/api/v1/my-requests/lookups/projects'))).toHaveLength(0);
    expect(portalCalls()).toHaveLength(0);
    expect(staffApi()).toHaveLength(0);
    expect(where((c) => c.url.includes('/procurement-management/') || c.url.includes('/api/v1/complaints'))).toHaveLength(0);
  });

  it('Save as draft POSTs my-requests, never the staff API, then lands on the list when there is no origin', async () => {
    mountForm(LIMITED);
    await screen.findByText('Customer & project');
    fireEvent.click(draftBtn());
    await waitFor(() => expect(posts()).toHaveLength(1));
    expect(posts()[0].body).toMatchObject({ customer_id: null });
    await waitFor(() => expect(nav.push).toHaveBeenCalledWith('/project-sales/sample-requests'));
    expect(nav.push.mock.calls.every((a) => !String(a[0]).startsWith('/portal'))).toBe(true);
    expect(staffApi()).toHaveLength(0);
    expect(portalCalls()).toHaveLength(0);
  });

  it('Save as draft lands on the ?from= origin when there is one', async () => {
    nav.search = `from=${encodeURIComponent('/project-sales/pr-1?tab=sample-requests')}`;
    mountForm(LIMITED);
    await screen.findByText('Customer & project');
    fireEvent.click(draftBtn());
    await waitFor(() => expect(nav.push).toHaveBeenCalledWith('/project-sales/pr-1?tab=sample-requests'));
    expect(staffApi()).toHaveLength(0);
  });

  it('Preview then Submit saves via PUT and POSTs .../<id>/submit on my-requests, then lands on the origin rule', async () => {
    detailNow = detail(READY);
    mountForm(LIMITED, { requestId: 'sr-5' });
    await screen.findByText('Customer & project');
    fireEvent.click(screen.getByRole('button', { name: 'Preview' }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('Preview sample request')).toBeInTheDocument();
    expect(where((c) => c.url.endsWith('/submit'))).toHaveLength(0);
    fireEvent.click(within(dialog).getByRole('button', { name: /^Submit$/ }));
    await waitFor(() => expect(where((c) => c.method === 'POST' && c.url === `${MINE}/sr-5/submit`)).toHaveLength(1));
    expect(where((c) => c.method === 'PUT' && c.url === `${MINE}/sr-5`)).toHaveLength(1);
    await waitFor(() => expect(nav.push).toHaveBeenCalledWith('/project-sales/sample-requests'));
    expect(nav.push.mock.calls.every((a) => !String(a[0]).startsWith('/portal'))).toBe(true);
    expect(staffApi()).toHaveLength(0);
  });

  it('Submit lands on the ?from= origin when there is one', async () => {
    nav.search = `from=${encodeURIComponent('/project-sales/pr-1?tab=sample-requests')}`;
    detailNow = detail(READY);
    mountForm(LIMITED, { requestId: 'sr-5' });
    await screen.findByText('Customer & project');
    fireEvent.click(screen.getByRole('button', { name: 'Preview' }));
    fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: /^Submit$/ }));
    await waitFor(() => expect(nav.push).toHaveBeenCalledWith('/project-sales/pr-1?tab=sample-requests'));
    expect(staffApi()).toHaveLength(0);
  });
});

describe('limited user, Sample Request edit loads from my-requests', () => {
  it('GETs my-requests/submissions/sample_request/<id>, shows the guided form, saves with PUT, never the staff API', async () => {
    mountForm(LIMITED, { requestId: 'sr-5' });
    expect(await screen.findByRole('button', { name: 'Preview' })).toBeInTheDocument();
    expect(screen.getByText('Ship to', { selector: 'span' })).toBeInTheDocument();
    expect(where((c) => c.method === 'GET' && c.url === `${MINE}/sr-5`).length).toBeGreaterThan(0);
    fireEvent.click(draftBtn());
    await waitFor(() => expect(where((c) => c.method === 'PUT' && c.url === `${MINE}/sr-5`)).toHaveLength(1));
    expect(staffApi()).toHaveLength(0);
    expect(portalCalls()).toHaveLength(0);
  });
});

describe('limited user, Sample Request view renders the portal form read-only', () => {
  it('a submitted request: portal form, disabled, loaded from my-requests, no staff tab strip, no staff API', async () => {
    mountDetail(LIMITED, { status: 'submitted', status_label: 'Submitted' });
    await waitFor(() => expect(document.getElementById('sr-customer')).not.toBeNull());
    expect((document.getElementById('sr-ship-to') as HTMLInputElement).disabled).toBe(true);
    expect(screen.getByLabelText('Sample request actions')).toBeInTheDocument();
    expect(screen.queryByRole('tab', { name: /Details/ })).toBeNull();
    expect(where((c) => c.method === 'GET' && c.url === `${MINE}/sr-5`).length).toBeGreaterThan(0);
    expect(staffApi()).toHaveLength(0);
    expect(portalCalls()).toHaveLength(0);
  });

  it('Cancel request POSTs my-requests/.../<id>/cancel', async () => {
    mountDetail(LIMITED, { status: 'submitted', status_label: 'Submitted' });
    fireEvent.click(await screen.findByText('Cancel request'));
    await waitFor(() => expect(where((c) => c.method === 'POST' && c.url === `${MINE}/sr-5/cancel`)).toHaveLength(1));
    expect(where((c) => c.url.endsWith('/move'))).toHaveLength(0);
  });
});

const PROJECT_ID = '5b0c1d2e-aaaa-4bbb-8ccc-0123456789ab';
describe('limited user, Sample Request seeded from a project (?project_id=)', () => {
  it('seeds project_id and the project title into the guided form and the saved body carries project_id', async () => {
    (getProject as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({ id: PROJECT_ID, project_code: 'PRJ-0001', title: 'Project One' });
    mountForm(LIMITED, { projectId: PROJECT_ID });
    expect(await screen.findByText(/PRJ-0001 - Project One/)).toBeInTheDocument();
    expect(document.body.textContent).not.toContain(PROJECT_ID);
    fireEvent.click(draftBtn());
    await waitFor(() => expect(posts()).toHaveLength(1));
    expect((posts()[0].body as { project_id?: string }).project_id).toBe(PROJECT_ID);
    expect(getProject).toHaveBeenCalledWith(PROJECT_ID);
    expect(staffApi()).toHaveLength(0);
  });

  it('no projectId: nothing is seeded', async () => {
    mountForm(LIMITED);
    await screen.findByText('Customer & project');
    expect(getProject).not.toHaveBeenCalled();
    expect((document.getElementById('sr-project-title') as HTMLInputElement).value).toBe('');
    fireEvent.click(draftBtn());
    await waitFor(() => expect(posts()).toHaveLength(1));
    expect((posts()[0].body as { project_id?: string | null }).project_id ?? null).toBeNull();
  });
});

describe('limited user, a refused save shows the message', () => {
  it('422 SAMPLE_REQUEST_PROJECT_NOT_ALLOWED: the form shows the message text, never the code', async () => {
    const message = 'Pick one of your own projects.';
    refusal = { status: 422, body: { message, code: 'SAMPLE_REQUEST_PROJECT_NOT_ALLOWED', details: { field: 'project_id' } } };
    mountForm(LIMITED);
    await screen.findByText('Customer & project');
    fireEvent.click(draftBtn());
    expect((await screen.findAllByText(message)).length).toBeGreaterThan(0);
    expect(document.body.textContent).not.toContain('SAMPLE_REQUEST_PROJECT_NOT_ALLOWED');
    const toasted = (toast.error as unknown as ReturnType<typeof vi.fn>).mock.calls.map((a) => String(a[0])).join('|');
    expect(toasted).not.toContain('SAMPLE_REQUEST_PROJECT_NOT_ALLOWED');
    expect(nav.push).not.toHaveBeenCalled();
    expect(staffApi()).toHaveLength(0);
  });
});

describe('staff keep today\'s Sample Request screens', () => {
  it('staff New is the CRM form: Add row, nothing sent to my-requests', async () => {
    mountForm(STAFF);
    expect(await screen.findByRole('button', { name: /Add row/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Submit sample request' })).toBeNull();
    expect(where((c) => c.url.startsWith('/api/v1/my-requests'))).toHaveLength(0);
  });

  it('staff detail keeps the tab strip and the staff GET, no portal form', async () => {
    mountDetail(STAFF, { status: 'submitted', status_label: 'Submitted' });
    expect(await screen.findByRole('tab', { name: /Details/ })).toBeInTheDocument();
    expect(document.getElementById('sr-customer')).toBeNull();
    await waitFor(() => expect(staffApi().length).toBeGreaterThan(0));
    expect(where((c) => c.url.startsWith(`${MINE}/sr-5`) && c.method === 'GET')).toHaveLength(0);
  });
});

/** S1: the CRM page header carries the one Back; the guided form renders no Back of its own and no /portal link. */
function expectNoOwnBack() {
  expect(screen.queryByRole('button', { name: /^Back/ })).toBeNull();
  expect(screen.queryByRole('link', { name: /Back/ })).toBeNull();
  for (const el of Array.from(document.querySelectorAll('[href]'))) {
    expect(el.getAttribute('href') ?? '').not.toContain('/portal');
  }
}

describe('limited user, Sample Request shows exactly one Back (the CRM header\'s)', () => {
  it('new form: no Back of its own, no /portal link', async () => {
    mountForm(LIMITED);
    await screen.findByText('Customer & project');
    expectNoOwnBack();
  });
  it('edit form: no Back of its own', async () => {
    mountForm(LIMITED, { requestId: 'sr-5' });
    await screen.findByRole('button', { name: 'Preview' });
    expectNoOwnBack();
  });
  it('read-only view: no Back of its own', async () => {
    mountDetail(LIMITED, { status: 'submitted', status_label: 'Submitted' });
    await screen.findByLabelText('Sample request actions');
    expectNoOwnBack();
  });
});
