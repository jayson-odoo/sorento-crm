/**
 * PORTAL-P4-REQUESTS S3 (P4-14, P4-24, P4-26): the Purchase Request / Sponsorship Form form for a LIMITED user
 * (holds `.view_own`, not `.view`) and for staff (control). Asserted at the HTTP seam (`apiFetch`) so it holds however
 * the coder splits hooks (the staff hooks are NOT mocked: a limited user must not reach them):
 *  - limited /new: "Save as draft" -> POST /api/v1/my-requests/submissions/{kind}; "Submit" -> POST .../{id}/submit;
 *    requestor options from /api/v1/my-requests/requestor-options (not the staff requestor-select endpoint).
 *  - `?from=<id>` pre-fills a NEW draft from GET /api/v1/my-requests/submissions/{kind}/<id> (Duplicate).
 *  - edit: only draft / rejected rows are editable; `?revise=1` on a revisable row freezes the requestor picker and
 *    "Send revision" -> POST .../{id}/revise.
 *  - staff /new: no draft buttons, original Create, requestors from the staff endpoint.
 */
import { submitVerb } from '@/lib/submission-status';
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const push = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => '/procurement-management/purchase-requests/new',
  useSearchParams: () => new URLSearchParams(window.location.search),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));
vi.mock('@/hooks/usePublicViewLinksEnabled', () => ({ usePublicViewLinksEnabled: () => false }));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
vi.mock('./PurchaseRequestAttachmentsSection', () => ({ __esModule: true, default: () => null }));
vi.mock('@/components/common/LookupBoundField', () => ({ __esModule: true, default: () => null }));
vi.mock('../services/purchaseRequestService', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  searchProjectsForLink: vi.fn().mockResolvedValue([]),
  getOrCreateViewLink: vi.fn(),
}));

let held = new Set<string>();
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => held.has(slug),
  useHasAnyPermission: (slugs: string[]) => slugs.some((s) => held.has(s)),
  usePermissions: () => ({ permissionSet: held, permissions: [...held], isLoading: false, isError: false }),
}));

// The picker: records that it loaded options, exposes its disabled state, picks one contact on click.
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (p: {
    fetchOptions?: (q: string) => Promise<unknown>;
    onChange: (v: string) => void;
    disabled?: boolean;
    value?: string;
    placeholder?: string;
  }) => {
    React.useEffect(() => {
      void p.fetchOptions?.('');
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);
    return (
      <button
        type="button"
        data-testid={p.fetchOptions ? 'requestor-picker' : `select-${p.placeholder ?? 'x'}`}
        data-disabled={String(!!p.disabled)}
        onClick={() => p.onChange('c1')}
      >
        {p.value ? `picked ${p.value}` : 'pick'}
      </button>
    );
  },
}));

type Kind = 'purchase_request' | 'sponsorship_form';
const KINDS: Array<{ kind: Kind; base: string; basePath: string }> = [
  { kind: 'purchase_request', base: 'procurement.purchase_requests', basePath: '/procurement-management/purchase-requests' },
  { kind: 'sponsorship_form', base: 'procurement.sponsorship_forms', basePath: '/procurement-management/sponsorship-forms' },
];

const calls: Array<{ url: string; method: string; body: unknown }> = [];
let sources: Record<string, Record<string, unknown>> = {};
const detail = (kind: Kind, over: Record<string, unknown> = {}) => ({
  id: 'pr-5',
  kind,
  request_type: kind,
  request_number: kind === 'purchase_request' ? 'PR26-0005' : 'SF26-0005',
  status: 'draft',
  approval_status: null,
  is_draft: true,
  is_editable: true,
  revision_no: 0,
  customer_name: 'OLD CUSTOMER',
  project_title: 'Old project',
  sales_type: 'project',
  purpose: 'old purpose',
  contact_id: 'c1',
  requested_by_contact_id: 'c1',
  requested_by_contact_name: 'Ann Sales',
  lines: [{ item_code: 'ITEM-A', quantity: 2, remark: null, unit_price: kind === 'sponsorship_form' ? 10 : null, total: kind === 'sponsorship_form' ? 20 : null }],
  attachments: [],
  revision: { enabled: false, allowed: false, used: 0, max: 0, remaining: 0, blocked_reason: null },
  ...over,
});

const apiFetch = vi.fn(async (url: string, init?: RequestInit) => {
  const method = (init?.method ?? 'GET').toUpperCase();
  let body: unknown = init?.body;
  if (typeof body === 'string') {
    try { body = JSON.parse(body); } catch { /* keep string */ }
  }
  calls.push({ url, method, body });
  const ok = (b: unknown) => new Response(JSON.stringify(b), { status: 200, headers: { 'content-type': 'application/json' } });
  if (url.startsWith('/api/v1/my-requests/requestor-options')) return ok({ items: [{ id: 'c1', name: 'Ann Sales' }], has_more: false });
  const mine = url.match(/^\/api\/v1\/my-requests\/submissions\/(purchase_request|sponsorship_form)(?:\/([^/?]+))?(\/submit|\/revise)?$/);
  if (mine) {
    const kind = mine[1] as Kind;
    const id = mine[2];
    if (method === 'GET' && id) return ok(sources[id] ?? detail(kind, { id }));
    if (mine[3] === '/submit') return ok(detail(kind, { id, status: 'submitted', is_draft: false }));
    if (mine[3] === '/revise') return ok({ submission: detail(kind, { id }), revision: {}, revision_no: 1 });
    return ok(detail(kind, { id: id ?? 'new-1' }));
  }
  const staffOne = url.match(/^\/api\/v1\/procurement\/purchase-requests\/([^/?]+)$/);
  if (staffOne && method === 'GET') return ok(sources[staffOne[1]] ?? detail('purchase_request', { id: staffOne[1] }));
  if (url.includes('requestor-select')) return ok({ items: [{ id: 'c1', name: 'Ann Sales' }], has_more: false });
  return ok({});
});
vi.mock('@/lib/api', () => ({ apiFetch: (...a: [string, RequestInit?]) => apiFetch(...a) }));

import PurchaseRequestForm from './PurchaseRequestForm';

const urls = (pred: (c: (typeof calls)[number]) => boolean) => calls.filter(pred);
const myPath = (k: Kind) => `/api/v1/my-requests/submissions/${k}`;

function mount(k: (typeof KINDS)[number], slugs: string[], props: { requestId?: string } = {}, search = '') {
  held = new Set(slugs);
  window.history.pushState({}, '', `${k.basePath}/new${search}`);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <PurchaseRequestForm
        {...props}
        defaultRequestType={k.kind}
        expectedRequestType={k.kind}
        successRedirectUrl={k.basePath}
      />
    </QueryClientProvider>,
  );
}

/** Click a button, then confirm in a dialog if one opens (either UX is fine). */
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

describe.each(KINDS)('$kind form, limited user', (k) => {
  const LIMITED = [`${k.base}.view_own`, `${k.base}.add`];

  it('/new offers Save as draft and Submit, not the staff Create', async () => {
    mount(k, LIMITED);
    expect(await screen.findByRole('button', { name: 'Save as draft' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^Submit/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Create$/ })).toBeNull();
  });

  it('loads requestors from my-requests/requestor-options, not the staff endpoint', async () => {
    mount(k, LIMITED);
    await waitFor(() => expect(urls((c) => c.url.startsWith('/api/v1/my-requests/requestor-options')).length).toBeGreaterThan(0));
    expect(urls((c) => c.url.includes('requestor') && !c.url.startsWith('/api/v1/my-requests/'))).toHaveLength(0);
  });

  it('?from=<id> pre-fills a NEW draft from that submission, saves nothing until asked, then POSTs a draft through my-requests', async () => {
    sources['pr-9'] = detail(k.kind, { id: 'pr-9', status: 'approved', is_draft: false, is_editable: false, customer_name: 'COPY ME SDN BHD', project_title: 'Copied project' });
    mount(k, LIMITED, {}, '?from=pr-9');
    await waitFor(() => expect((screen.getByPlaceholderText('Project title') as HTMLInputElement).value).toBe('Copied project'));
    expect(urls((c) => c.url === `${myPath(k.kind)}/pr-9` && c.method === 'GET').length).toBeGreaterThan(0);
    expect(urls((c) => c.method !== 'GET')).toHaveLength(0);
    fireEvent.click(await screen.findByRole('button', { name: 'Save as draft' }));
    await waitFor(() => expect(urls((c) => c.method === 'POST' && c.url === myPath(k.kind))).toHaveLength(1));
    const body = urls((c) => c.method === 'POST')[0].body as { fields: Record<string, unknown>; products?: unknown[] };
    expect(body.fields).toMatchObject({ project_title: 'Copied project' });
    expect(body.products).toMatchObject([{ item_code: 'ITEM-A' }]);
    expect(urls((c) => c.url.startsWith('/api/v1/procurement/') && c.method !== 'GET')).toHaveLength(0);
  });

  it('"Submit" saves the draft then POSTs .../{id}/submit through my-requests', async () => {
    sources['pr-9'] = detail(k.kind, { id: 'pr-9', status: 'approved', is_draft: false, is_editable: false });
    mount(k, LIMITED, {}, '?from=pr-9');
    await waitFor(() => expect((screen.getByPlaceholderText('Project title') as HTMLInputElement).value).toBe('Old project'));
    await clickThrough(/^Submit/);
    await waitFor(() =>
      expect(urls((c) => c.method === 'POST' && /^\/api\/v1\/my-requests\/submissions\/[a-z_]+\/[^/]+\/submit$/.test(c.url))).toHaveLength(1),
    );
    expect(urls((c) => c.url.startsWith('/api/v1/procurement/') && c.method !== 'GET')).toHaveLength(0);
  });
});

describe.each(KINDS)('$kind form, limited user, edit', (k) => {
  const LIMITED = [`${k.base}.view_own`, `${k.base}.add`];

  it('a draft row saves through PUT my-requests/submissions/{kind}/{id}', async () => {
    sources['pr-5'] = detail(k.kind, { id: 'pr-5', status: 'draft' });
    mount(k, LIMITED, { requestId: 'pr-5' });
    fireEvent.click(await screen.findByRole('button', { name: 'Save as draft' }));
    await waitFor(() => expect(urls((c) => c.method === 'PUT' && c.url === `${myPath(k.kind)}/pr-5`)).toHaveLength(1));
    expect(urls((c) => c.url.startsWith('/api/v1/procurement/') && c.method !== 'GET')).toHaveLength(0);
  });

  it('a rejected row is editable (send-back button available)', async () => {
    sources['pr-5'] = detail(k.kind, { id: 'pr-5', status: 'submitted', approval_status: 'rejected', is_draft: true });
    mount(k, LIMITED, { requestId: 'pr-5' });
    expect(await screen.findByRole('button', { name: new RegExp(`^${submitVerb('rejected')}`) })).toBeInTheDocument();
  });

  it.each([
    ['submitted', 'pending'],
    ['submitted', 'approved'],
    ['processed_by_cs', 'approved'],
  ])('a %s / %s row offers no save or submit when not revising', async (status, approval) => {
    sources['pr-5'] = detail(k.kind, { id: 'pr-5', status, approval_status: approval, is_draft: false, is_editable: false });
    mount(k, LIMITED, { requestId: 'pr-5' });
    await screen.findByPlaceholderText('Project title');
    expect(screen.queryByRole('button', { name: 'Save as draft' })).toBeNull();
    expect(screen.queryByRole('button', { name: /^Submit/ })).toBeNull();
    expect(screen.queryAllByRole('button', { name: /^Update/ })).toHaveLength(0);
  });

  it('?revise=1 on a revisable row freezes the requestor picker and Send revision POSTs .../revise', async () => {
    sources['pr-5'] = detail(k.kind, {
      id: 'pr-5',
      status: 'submitted',
      approval_status: 'approved',
      is_draft: false,
      is_editable: false,
      revision: { enabled: true, allowed: true, used: 0, max: 3, remaining: 3, blocked_reason: null },
    });
    mount(k, LIMITED, { requestId: 'pr-5' }, '?revise=1');
    await screen.findByPlaceholderText('Project title');
    await waitFor(() => expect(screen.getByTestId('requestor-picker').getAttribute('data-disabled')).toBe('true'));
    fireEvent.change(await screen.findByPlaceholderText('Project title'), { target: { value: 'Revised project' } });
    const reason = document.getElementById('revision_reason') ?? screen.getByLabelText(/reason/i);
    fireEvent.change(reason, { target: { value: 'wrong title' } });
    await clickThrough(/Send revision/);
    await waitFor(() => expect(urls((c) => c.method === 'POST' && c.url === `${myPath(k.kind)}/pr-5/revise`)).toHaveLength(1));
    const body = urls((c) => c.url.endsWith('/revise'))[0].body as Record<string, unknown>;
    expect(body).toMatchObject({ reason: 'wrong title', expected_revision_no: 0 });
  });

  it('?revise=1 where the server refuses revision offers no Send revision', async () => {
    sources['pr-5'] = detail(k.kind, { id: 'pr-5', status: 'submitted', approval_status: 'approved', is_draft: false, is_editable: false });
    mount(k, LIMITED, { requestId: 'pr-5' }, '?revise=1');
    await screen.findByPlaceholderText('Project title');
    expect(screen.queryByRole('button', { name: /Send revision/ })).toBeNull();
  });
});

describe.each(KINDS)('$kind form, staff user /new (control, P4-26)', (k) => {
  it('shows Create, no draft buttons, and never touches my-requests', async () => {
    mount(k, [`${k.base}.view`, `${k.base}.add`, `${k.base}.edit`]);
    await screen.findByPlaceholderText('Project title');
    expect(screen.queryByRole('button', { name: 'Save as draft' })).toBeNull();
    expect(screen.queryByRole('button', { name: /^Submit/ })).toBeNull();
    expect(screen.getByRole('button', { name: /^Create$/ })).toBeInTheDocument();
    expect(urls((c) => c.url.startsWith('/api/v1/my-requests/'))).toHaveLength(0);
  });
});
