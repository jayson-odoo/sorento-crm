/**
 * PORTAL-P4-REQUESTS S2 (P4-24, P4-14, P4-26): the Complaint form for a LIMITED user (holds `.view_own`, not
 * `.view`) and for staff (control). Asserted at the HTTP seam (`apiFetch`) so it holds however the coder splits hooks:
 *  - limited /new: no "Technical Team" card (contact id, space id, root cause, resolution, technical response);
 *    "Save as draft" -> POST /api/v1/my-requests/submissions/complaint (then PUT .../{id}); "Submit" -> POST .../{id}/submit.
 *  - `?from=<id>` pre-fills a NEW draft from GET /api/v1/my-requests/submissions/complaint/<id> (Duplicate).
 *  - edit: only draft / rejected rows are editable; `?revise=1` on a revisable row shows the reason box
 *    (`id="revision_reason"`) and "Send revision" -> POST .../{id}/revise.
 *  - staff /new: no draft buttons, the Technical Team card present, nothing sent to my-requests.
 * Modelled on StockInquiryForm.requestScope.test.tsx.
 */
import { submitVerb } from '@/lib/submission-status';
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const push = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => '/complaint-management/complaints/new',
  useSearchParams: () => new URLSearchParams(window.location.search),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));
vi.mock('@/hooks/usePublicViewLinksEnabled', () => ({ usePublicViewLinksEnabled: () => false }));
vi.mock('./ComplaintManualAttachmentsSection', () => ({ __esModule: true, default: () => null }));
vi.mock('@/components/common/ListPager', () => ({ __esModule: true, default: () => null }));
vi.mock('@/components/common/LookupBoundField', () => ({ __esModule: true, default: () => null }));
vi.mock('@/app/(protected)/complaint-management/complaint-root-causes/hooks/useComplaintRootCauses', () => ({
  useComplaintRootCausesSelect: () => ({ data: [], error: null, refetch: vi.fn() }),
}));
vi.mock('@/app/(protected)/complaint-management/complaint-resolutions/hooks/useComplaintResolutions', () => ({
  useComplaintResolutionsSelect: () => ({ data: [], error: null, refetch: vi.fn() }),
}));

let held = new Set<string>();
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => held.has(slug),
  useHasAnyPermission: (slugs: string[]) => slugs.some((s) => held.has(s)),
  usePermissions: () => ({ permissionSet: held, permissions: [...held], isLoading: false, isError: false }),
}));
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: () => <span data-testid="select-stub" />,
}));

const calls: Array<{ url: string; method: string; body: unknown }> = [];
const detail = (over: Record<string, unknown> = {}) => ({
  id: 'cp-5',
  kind: 'complaint',
  status: 'draft',
  is_draft: true,
  is_editable: true,
  revision_no: 0,
  customer_name: 'OLD CUSTOMER',
  defect_description: 'old defect',
  delivery_order_number: 'DO-OLD',
  product_lines: [],
  attachments: [],
  revision: { enabled: false, allowed: false, used: 0, max: 0, remaining: 0, blocked_reason: null },
  ...over,
});
let sources: Record<string, Record<string, unknown>> = {};

const apiFetch = vi.fn(async (url: string, init?: RequestInit) => {
  const method = (init?.method ?? 'GET').toUpperCase();
  let body: unknown = init?.body;
  if (typeof body === 'string') {
    try { body = JSON.parse(body); } catch { /* keep string */ }
  }
  calls.push({ url, method, body });
  const ok = (b: unknown) => new Response(JSON.stringify(b), { status: 200, headers: { 'content-type': 'application/json' } });
  const mine = url.match(/^\/api\/v1\/my-requests\/submissions\/complaint(?:\/([^/?]+))?(\/submit|\/revise)?$/);
  if (mine) {
    const id = mine[1];
    if (method === 'GET' && id) return ok(sources[id] ?? detail({ id }));
    if (mine[2] === '/submit') return ok(detail({ id, status: 'submitted', is_draft: false }));
    if (mine[2] === '/revise') return ok({ submission: detail({ id }), revision: {}, revision_no: 1 });
    return ok(detail({ id: id ?? 'new-1' }));
  }
  const staffOne = url.match(/^\/api\/v1\/complaints-management\/complaints\/([^/?]+)$/);
  if (staffOne && method === 'GET') return ok(sources[staffOne[1]] ?? detail({ id: staffOne[1] }));
  return ok({});
});
vi.mock('@/lib/api', () => ({ apiFetch: (...a: [string, RequestInit?]) => apiFetch(...a) }));

import ComplaintForm from './ComplaintForm';

const LIMITED = ['complaint_management.complaints.view_own', 'complaint_management.complaints.add'];
const STAFF = [
  'complaint_management.complaints.view',
  'complaint_management.complaints.add',
  'complaint_management.complaints.edit',
];
const urls = (pred: (c: (typeof calls)[number]) => boolean) => calls.filter(pred);
const STAFF_ONLY_PLACEHOLDERS = [
  'Respond.io contact ID',
  'Respond.io space ID',
  'Enter technical team response to send to customer',
  'Select root cause (optional)',
  'Select resolution (optional)',
];

function mount(slugs: string[], props: { complaintId?: string } = {}, search = '') {
  held = new Set(slugs);
  window.history.pushState({}, '', `/complaint-management/complaints/new${search}`);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ComplaintForm {...props} />
    </QueryClientProvider>,
  );
}

async function fillBasics() {
  fireEvent.change(await screen.findByPlaceholderText('Enter customer name'), { target: { value: 'ZZT Customer' } });
  fireEvent.change(screen.getByPlaceholderText('Enter detailed defect description'), { target: { value: 'tap leaks' } });
}

async function clickThrough(name: RegExp) {
  fireEvent.click(await screen.findByRole('button', { name }));
  await act(async () => { await new Promise((r) => setTimeout(r, 150)); });
  const dialog = screen.queryByRole('dialog') ?? screen.queryByRole('alertdialog');
  if (dialog) {
    const confirm = Array.from(dialog.querySelectorAll('button')).find((b) => /submit|confirm|yes|send/i.test(b.textContent ?? ''));
    if (confirm) fireEvent.click(confirm);
  }
}

beforeEach(() => {
  cleanup();
  calls.length = 0;
  sources = {};
  vi.clearAllMocks();
});

describe('limited user, /new', () => {
  it('has no Technical Team card and none of its fields', async () => {
    mount(LIMITED);
    await screen.findByPlaceholderText('Enter customer name');
    expect(screen.queryAllByText(/Tecnical Team|Technical Team/)).toHaveLength(0);
    for (const p of STAFF_ONLY_PLACEHOLDERS) expect(screen.queryByPlaceholderText(p), p).toBeNull();
    expect(screen.queryAllByText('Root Cause')).toHaveLength(0);
    expect(screen.queryAllByText('Resolution')).toHaveLength(0);
    expect(screen.queryAllByRole('button', { name: /Update & Reply/ })).toHaveLength(0);
  });

  it('"Save as draft" POSTs a draft through my-requests with the typed fields and no staff-only field', async () => {
    mount(LIMITED);
    await fillBasics();
    fireEvent.click(await screen.findByRole('button', { name: 'Save as draft' }));
    await waitFor(() => expect(urls((c) => c.method === 'POST' && c.url === '/api/v1/my-requests/submissions/complaint')).toHaveLength(1));
    const body = urls((c) => c.method === 'POST')[0].body as { fields: Record<string, unknown> };
    expect(body.fields).toMatchObject({ customer_name: 'ZZT Customer', defect_description: 'tap leaks' });
    for (const k of ['technical_team_response', 'root_cause_id', 'resolution_id', 'contact_id', 'space_id']) {
      expect(body.fields, k).not.toHaveProperty(k);
    }
    expect(urls((c) => c.url.startsWith('/api/v1/complaints-management') && c.method !== 'GET')).toHaveLength(0);
  });

  it('"Submit" saves the draft then POSTs .../{id}/submit through my-requests', async () => {
    mount(LIMITED);
    await fillBasics();
    await clickThrough(/^Submit/);
    await waitFor(() =>
      expect(urls((c) => c.method === 'POST' && /^\/api\/v1\/my-requests\/submissions\/complaint\/[^/]+\/submit$/.test(c.url))).toHaveLength(1),
    );
    expect(urls((c) => c.url.startsWith('/api/v1/complaints-management') && c.method !== 'GET')).toHaveLength(0);
  });

  it('?from=<id> pre-fills a NEW draft from that submission and saves nothing until asked', async () => {
    sources['cp-9'] = detail({ id: 'cp-9', status: 'processed_by_cs', is_draft: false, is_editable: false, customer_name: 'DUP CUSTOMER', defect_description: 'copy me' });
    mount(LIMITED, {}, '?from=cp-9');
    await waitFor(() => expect((screen.getByPlaceholderText('Enter customer name') as HTMLInputElement).value).toBe('DUP CUSTOMER'));
    expect((screen.getByPlaceholderText('Enter detailed defect description') as HTMLTextAreaElement).value).toBe('copy me');
    expect(urls((c) => c.url === '/api/v1/my-requests/submissions/complaint/cp-9' && c.method === 'GET').length).toBeGreaterThan(0);
    expect(urls((c) => c.method !== 'GET')).toHaveLength(0);
    fireEvent.click(await screen.findByRole('button', { name: 'Save as draft' }));
    await waitFor(() => expect(urls((c) => c.method === 'POST' && c.url === '/api/v1/my-requests/submissions/complaint')).toHaveLength(1));
  });
});

describe('limited user, edit', () => {
  it('a draft row saves through PUT my-requests/submissions/complaint/{id}', async () => {
    sources['cp-5'] = detail({ id: 'cp-5', status: 'draft' });
    mount(LIMITED, { complaintId: 'cp-5' });
    fireEvent.click(await screen.findByRole('button', { name: 'Save as draft' }));
    await waitFor(() => expect(urls((c) => c.method === 'PUT' && c.url === '/api/v1/my-requests/submissions/complaint/cp-5')).toHaveLength(1));
  });

  it('a rejected row is editable (Submit available)', async () => {
    sources['cp-5'] = detail({ id: 'cp-5', status: 'rejected', is_draft: true });
    mount(LIMITED, { complaintId: 'cp-5' });
    expect(await screen.findByRole('button', { name: new RegExp(`^${submitVerb('rejected')}`) })).toBeInTheDocument();
  });

  it.each(['submitted', 'responded', 'approved', 'processed_by_cs'])('a %s row offers no save or submit when not revising', async (status) => {
    sources['cp-5'] = detail({ id: 'cp-5', status, is_draft: false, is_editable: false });
    mount(LIMITED, { complaintId: 'cp-5' });
    await screen.findByPlaceholderText('Enter customer name');
    expect(screen.queryByRole('button', { name: 'Save as draft' })).toBeNull();
    expect(screen.queryByRole('button', { name: /^Submit/ })).toBeNull();
    expect(screen.queryAllByRole('button', { name: /Update Complaint|Update & Reply/ })).toHaveLength(0);
  });

  it('?revise=1 on a revisable row: Send revision POSTs .../revise with the reason', async () => {
    sources['cp-5'] = detail({
      id: 'cp-5',
      status: 'processed_by_cs',
      is_draft: false,
      is_editable: false,
      revision: { enabled: true, allowed: true, used: 0, max: 3, remaining: 3, blocked_reason: null },
    });
    mount(LIMITED, { complaintId: 'cp-5' }, '?revise=1');
    await screen.findByPlaceholderText('Enter customer name');
    fireEvent.change(await screen.findByPlaceholderText('Enter detailed defect description'), { target: { value: 'new defect' } });
    const reason = await waitFor(() => {
      const el = document.getElementById('revision_reason');
      expect(el).not.toBeNull();
      return el as HTMLElement;
    });
    fireEvent.change(reason, { target: { value: 'wrong defect' } });
    await clickThrough(/Send revision/);
    await waitFor(() => expect(urls((c) => c.method === 'POST' && c.url === '/api/v1/my-requests/submissions/complaint/cp-5/revise')).toHaveLength(1));
    const body = urls((c) => c.url.endsWith('/revise'))[0].body as Record<string, unknown>;
    expect(body).toMatchObject({ reason: 'wrong defect', expected_revision_no: 0 });
    expect((body.fields as Record<string, unknown>).defect_description).toBe('new defect');
  });

  it('?revise=1 on a row the server will not revise offers no Send revision', async () => {
    sources['cp-5'] = detail({ id: 'cp-5', status: 'processed_by_cs', is_draft: false, is_editable: false });
    mount(LIMITED, { complaintId: 'cp-5' }, '?revise=1');
    await screen.findByPlaceholderText('Enter customer name');
    expect(screen.queryByRole('button', { name: /Send revision/ })).toBeNull();
    expect(document.getElementById('revision_reason')).toBeNull();
  });
});

describe('staff user, /new (control, P4-26)', () => {
  it('keeps the Technical Team card, shows no draft buttons, and never touches my-requests', async () => {
    mount(STAFF);
    await screen.findByPlaceholderText('Enter customer name');
    expect(screen.getByPlaceholderText('Respond.io contact ID')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Enter technical team response to send to customer')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Save as draft' })).toBeNull();
    expect(screen.queryByRole('button', { name: /^Submit/ })).toBeNull();
    expect(screen.getByRole('button', { name: 'Create Complaint' })).toBeInTheDocument();
    expect(urls((c) => c.url.startsWith('/api/v1/my-requests/'))).toHaveLength(0);
  });
});
