/**
 * PORTAL-P4-REQUESTS R3a (form parity, PAR-1/3/5): a LIMITED user (`view_own`, not `view`) creates, edits and VIEWS a
 * Sample Request through the PORTAL's own SampleRequestForm (app/(auth)/portal/components), wired to
 * `/api/v1/my-requests` by an injected client. Entry points are the components the pages render: SampleRequestForm
 * (new with ?project_id= / edit), and SampleRequestDetailTabs + SampleRequestDetail (view). Staff keep today's screens.
 *
 * Marker that tells the PORTAL form from the CRM one: the portal's submit button reads "Submit sample request"
 * (the CRM reads "Submit"), its item card is titled "Items" with an "Add item" button (the CRM has "Line items" and
 * "Add row"), and the portal shows no "Sales Person" read-only field.
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { EMPTY_FORM, blankLine, payloadFromState } from '@/lib/sample-request-form';

const nav = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn() }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: nav.push, replace: nav.replace, back: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => '/project-sales/sample-requests/new',
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
vi.mock('@/app/(protected)/project-sales/_shared/services/projectService', () => ({ getProject: vi.fn() }));

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
  pending.getCurrentPendingAction.mockResolvedValue({ pending: null, last_outcome: null });
});

describe('limited user, New Sample Request renders the portal form', () => {
  it('is the portal form (Submit sample request, Items / Add item), not the CRM one', async () => {
    mountForm(LIMITED);
    expect(await screen.findByRole('button', { name: 'Submit sample request' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Add item/ })).toBeInTheDocument();
    expect(screen.queryByText('Sales Person')).toBeNull();
    expect(screen.queryByRole('button', { name: /Add row/ })).toBeNull();
  });

  it('customer search, product search and registered projects go to my-requests only', async () => {
    mountForm(LIMITED);
    await screen.findByRole('button', { name: 'Submit sample request' });
    fireEvent.change(screen.getByLabelText(/^Customer Name/), { target: { value: 'ZZ' } });
    await waitFor(() => expect(where((c) => c.url.startsWith('/api/v1/my-requests/sample-request/customers')).length).toBeGreaterThan(0), { timeout: 3000 });
    fireEvent.change(screen.getByLabelText('Item code'), { target: { value: 'TI' } });
    await waitFor(() => expect(where((c) => c.url.startsWith('/api/v1/my-requests/sample-request/products')).length).toBeGreaterThan(0), { timeout: 3000 });
    fireEvent.change(screen.getByPlaceholderText('Search your registered projects'), { target: { value: 'PR' } });
    await waitFor(() => expect(where((c) => c.url.startsWith('/api/v1/my-requests/lookups/projects')).length).toBeGreaterThan(0), { timeout: 3000 });
    expect(portalCalls()).toHaveLength(0);
    expect(staffApi()).toHaveLength(0);
  });

  it('Save as draft POSTs the portal payload, then router.replace goes to the CRM detail (never /portal)', async () => {
    mountForm(LIMITED);
    fireEvent.change(await screen.findByLabelText(/^Ship To/), { target: { value: 'ZZT Site' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save as draft' }));
    await waitFor(() => expect(where((c) => c.method === 'POST' && c.url === MINE)).toHaveLength(1));
    const expected = payloadFromState({ ...EMPTY_FORM, ship_to_name: 'ZZT Site', lines: [blankLine()] });
    expect(where((c) => c.method === 'POST' && c.url === MINE)[0].body).toEqual(expected);
    await waitFor(() => expect(nav.replace).toHaveBeenCalledWith('/project-sales/sample-requests/new-1'));
    expect(nav.replace.mock.calls.every((a) => !String(a[0]).startsWith('/portal'))).toBe(true);
    expect(staffApi()).toHaveLength(0);
    expect(portalCalls()).toHaveLength(0);
  });

  it('Submit POSTs .../<id>/submit then pushes the CRM list', async () => {
    mountForm(LIMITED, { requestId: 'sr-5' });
    fireEvent.click(await screen.findByRole('button', { name: 'Submit sample request' }));
    await waitFor(() => expect(where((c) => c.method === 'POST' && c.url === `${MINE}/sr-5/submit`)).toHaveLength(1));
    await waitFor(() => expect(nav.push).toHaveBeenCalledWith('/project-sales/sample-requests'));
    expect(nav.push.mock.calls.every((a) => !String(a[0]).startsWith('/portal'))).toBe(true);
    expect(staffApi()).toHaveLength(0);
  });
});

describe('limited user, Sample Request edit loads from my-requests', () => {
  it('GETs my-requests/submissions/sample_request/<id>, shows the portal form, saves with PUT, never the staff API', async () => {
    mountForm(LIMITED, { requestId: 'sr-5' });
    expect(await screen.findByRole('button', { name: 'Submit sample request' })).toBeInTheDocument();
    expect(where((c) => c.method === 'GET' && c.url === `${MINE}/sr-5`).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole('button', { name: 'Save as draft' }));
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
  it('seeds project_id and the project title into the PORTAL form and the saved body carries project_id', async () => {
    (getProject as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({ id: PROJECT_ID, project_code: 'PRJ-0001', title: 'Project One' });
    mountForm(LIMITED, { projectId: PROJECT_ID });
    expect(await screen.findByRole('button', { name: 'Submit sample request' })).toBeInTheDocument();
    await waitFor(() => expect((document.getElementById('sr-project-title') as HTMLInputElement).value).toBe('Project One'));
    expect(document.body.textContent).not.toContain(PROJECT_ID);
    fireEvent.click(screen.getByRole('button', { name: 'Save as draft' }));
    await waitFor(() => expect(where((c) => c.method === 'POST' && c.url === MINE)).toHaveLength(1));
    expect((where((c) => c.method === 'POST' && c.url === MINE)[0].body as { project_id?: string }).project_id).toBe(PROJECT_ID);
    expect(getProject).toHaveBeenCalledWith(PROJECT_ID);
  });

  it('no projectId: nothing is seeded', async () => {
    mountForm(LIMITED);
    await screen.findByRole('button', { name: 'Submit sample request' });
    expect(getProject).not.toHaveBeenCalled();
    expect((document.getElementById('sr-project-title') as HTMLInputElement).value).toBe('');
  });
});

describe('limited user, a refused save shows the message', () => {
  it('422 SAMPLE_REQUEST_PROJECT_NOT_ALLOWED: toast.error carries the message text, never the code', async () => {
    const message = 'Pick one of your own projects.';
    refusal = { status: 422, body: { message, code: 'SAMPLE_REQUEST_PROJECT_NOT_ALLOWED', details: { field: 'project_id' } } };
    mountForm(LIMITED);
    fireEvent.click(await screen.findByRole('button', { name: 'Save as draft' }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith(message));
    const shown = (toast.error as unknown as ReturnType<typeof vi.fn>).mock.calls.map((a) => String(a[0])).join('|');
    expect(shown).not.toContain('SAMPLE_REQUEST_PROJECT_NOT_ALLOWED');
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

/** S1: the CRM page header carries the one Back; the embedded portal form shows none of its own and no /portal link. */
function expectNoOwnBack() {
  expect(screen.queryByRole('button', { name: /^Back/ })).toBeNull();
  expect(screen.queryByRole('link', { name: /Back/ })).toBeNull();
  for (const el of Array.from(document.querySelectorAll('[href]'))) {
    expect(el.getAttribute('href') ?? '').not.toContain('/portal');
  }
}
/** Item 4: a NEW embedded form opens on its first card, with no empty header row above it. */
function expectNoEmptyHeaderRow(container: HTMLElement) {
  const shell = container.firstElementChild as HTMLElement;
  const first = shell.firstElementChild as HTMLElement;
  expect(first.childElementCount).toBeGreaterThan(0);
  expect(first.querySelector('[data-slot="card"]') ?? first.closest('[data-slot="card"]')).not.toBeNull();
}

describe('limited user, Sample Request shows exactly one Back (the CRM header\'s)', () => {
  it('new form: no Back of its own, no /portal link, no empty header row', async () => {
    const { container } = mountForm(LIMITED);
    await screen.findByRole('button', { name: 'Submit sample request' });
    expectNoOwnBack();
    expectNoEmptyHeaderRow(container);
  });
  it('edit form: no Back of its own', async () => {
    mountForm(LIMITED, { requestId: 'sr-5' });
    await screen.findByRole('button', { name: 'Submit sample request' });
    expectNoOwnBack();
  });
  it('read-only view: no Back of its own', async () => {
    mountDetail(LIMITED, { status: 'submitted', status_label: 'Submitted' });
    await screen.findByLabelText('Sample request actions');
    expectNoOwnBack();
  });
});
