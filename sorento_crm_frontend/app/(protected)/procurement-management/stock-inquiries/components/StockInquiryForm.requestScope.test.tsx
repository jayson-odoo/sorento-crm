/**
 * PORTAL-P4-REQUESTS S1 (P4-24, P4-26): the Stock Inquiry form for a LIMITED user (holds `.view_own`, not `.view`)
 * and for staff (control). Asserted at the HTTP seam (`apiFetch`) so it holds however the coder splits hooks:
 *  - limited /new: no purchasing response field; "Save as draft" -> POST /api/v1/my-requests/submissions/stock_inquiry
 *    (then PUT .../{id}); "Submit" -> POST .../{id}/submit; requestor options from /api/v1/my-requests/requestor-options.
 *  - `?from=<id>` pre-fills a NEW draft from GET /api/v1/my-requests/submissions/stock_inquiry/<id> (Duplicate).
 *  - edit: only draft / rejected rows are editable; `?revise=1` on a revisable row freezes the requestor picker and
 *    "Send revision" -> POST .../{id}/revise.
 *  - staff /new: no draft buttons, purchasing response present, requestors from the staff endpoint.
 */
import React from 'react';
import { submitVerb } from '@/lib/submission-status';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const push = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => '/procurement-management/stock-inquiries/new',
  useSearchParams: () => new URLSearchParams(window.location.search),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));
vi.mock('@/hooks/usePublicViewLinksEnabled', () => ({ usePublicViewLinksEnabled: () => false }));
vi.mock('./StockInquiryAttachmentsSection', () => ({ __esModule: true, default: () => null }));

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
  }) => {
    React.useEffect(() => {
      void p.fetchOptions?.('');
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);
    return (
      <button type="button" data-testid="requestor-picker" data-disabled={String(!!p.disabled)} onClick={() => p.onChange('c1')}>
        {p.value ? `picked ${p.value}` : 'pick requestor'}
      </button>
    );
  },
}));

const calls: Array<{ url: string; method: string; body: unknown }> = [];
const detail = (over: Record<string, unknown> = {}) => ({
  id: 'si-5',
  kind: 'stock_inquiry',
  status: 'draft',
  is_draft: true,
  is_editable: true,
  revision_no: 0,
  product_code: 'OLD-1',
  item_description: 'old desc',
  quantity: '2',
  contact_id: 'c1',
  salesperson_contact_id: 'c1',
  salesperson_contact_name: 'Ann Sales',
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
  if (url.startsWith('/api/v1/my-requests/requestor-options')) return ok({ items: [{ id: 'c1', name: 'Ann Sales' }], has_more: false });
  const mine = url.match(/^\/api\/v1\/my-requests\/submissions\/stock_inquiry(?:\/([^/?]+))?(\/submit|\/revise)?$/);
  if (mine) {
    const id = mine[1];
    if (method === 'GET' && id) return ok(sources[id] ?? detail({ id }));
    if (mine[2] === '/submit') return ok(detail({ id, status: 'pending_purchasing', is_draft: false }));
    if (mine[2] === '/revise') return ok({ submission: detail({ id }), revision: {}, revision_no: 1 });
    return ok(detail({ id: id ?? 'new-1' }));
  }
  const staffOne = url.match(/^\/api\/v1\/procurement\/stock-inquiries\/([^/?]+)$/);
  if (staffOne && method === 'GET') return ok(sources[staffOne[1]] ?? detail({ id: staffOne[1] }));
  if (url.includes('requestor')) return ok({ items: [{ id: 'c1', name: 'Ann Sales' }], has_more: false });
  return ok({});
});
vi.mock('@/lib/api', () => ({ apiFetch: (...a: [string, RequestInit?]) => apiFetch(...a) }));

import StockInquiryForm from './StockInquiryForm';

const LIMITED = ['procurement.stock_inquiries.view_own', 'procurement.stock_inquiries.add'];
const STAFF = ['procurement.stock_inquiries.view', 'procurement.stock_inquiries.add', 'procurement.stock_inquiries.edit'];
const urls = (pred: (c: (typeof calls)[number]) => boolean) => calls.filter(pred);

function mount(slugs: string[], props: { inquiryId?: string } = {}, search = '') {
  held = new Set(slugs);
  window.history.pushState({}, '', `/procurement-management/stock-inquiries/new${search}`);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <StockInquiryForm {...props} />
    </QueryClientProvider>,
  );
}

async function fillBasics() {
  fireEvent.change(await screen.findByPlaceholderText('Code'), { target: { value: 'ABC-9' } });
  fireEvent.change(screen.getByPlaceholderText('Description'), { target: { value: 'ten boxes' } });
  fireEvent.change(screen.getByPlaceholderText('Quantity'), { target: { value: '10' } });
  fireEvent.click(screen.getByTestId('requestor-picker'));
}

/** Click a button, then confirm in a dialog if one opens (the portal confirms a submit; either UX is fine). */
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
  it('has no purchasing response field', async () => {
    mount(LIMITED);
    await screen.findByPlaceholderText('Code');
    expect(screen.queryByPlaceholderText('For purchasing use')).toBeNull();
    expect(screen.queryByText(/reply by purchasing/i)).toBeNull();
  });

  it('loads requestors from my-requests/requestor-options, not the staff endpoint', async () => {
    mount(LIMITED);
    await waitFor(() => expect(urls((c) => c.url.startsWith('/api/v1/my-requests/requestor-options')).length).toBeGreaterThan(0));
    expect(urls((c) => c.url.includes('requestor') && !c.url.startsWith('/api/v1/my-requests/'))).toHaveLength(0);
  });

  it('"Save as draft" POSTs a draft through my-requests with the typed fields and no purchasing_response', async () => {
    mount(LIMITED);
    await fillBasics();
    fireEvent.click(await screen.findByRole('button', { name: 'Save as draft' }));
    await waitFor(() => expect(urls((c) => c.method === 'POST' && c.url === '/api/v1/my-requests/submissions/stock_inquiry')).toHaveLength(1));
    const body = urls((c) => c.method === 'POST')[0].body as { fields: Record<string, unknown> };
    expect(body.fields).toMatchObject({ product_code: 'ABC-9', item_description: 'ten boxes' });
    expect(body.fields).not.toHaveProperty('purchasing_response');
    expect(urls((c) => c.url.startsWith('/api/v1/procurement/stock-inquiries') && c.method !== 'GET')).toHaveLength(0);
  });

  it('"Submit" saves the draft then POSTs .../{id}/submit through my-requests', async () => {
    mount(LIMITED);
    await fillBasics();
    await clickThrough(/^Submit/);
    await waitFor(() =>
      expect(urls((c) => c.method === 'POST' && /^\/api\/v1\/my-requests\/submissions\/stock_inquiry\/[^/]+\/submit$/.test(c.url))).toHaveLength(1),
    );
    expect(urls((c) => c.url.startsWith('/api/v1/procurement/stock-inquiries') && c.method !== 'GET')).toHaveLength(0);
  });

  it('?from=<id> pre-fills a NEW draft from that submission and saves nothing until asked', async () => {
    sources['si-9'] = detail({ id: 'si-9', status: 'responded', is_draft: false, is_editable: false, product_code: 'DUP-1', item_description: 'copy me', quantity: '4' });
    mount(LIMITED, {}, '?from=si-9');
    await waitFor(() => expect((screen.getByPlaceholderText('Code') as HTMLInputElement).value).toBe('DUP-1'));
    expect((screen.getByPlaceholderText('Description') as HTMLTextAreaElement).value).toBe('copy me');
    expect(urls((c) => c.url === '/api/v1/my-requests/submissions/stock_inquiry/si-9' && c.method === 'GET').length).toBeGreaterThan(0);
    expect(urls((c) => c.method !== 'GET')).toHaveLength(0);
    fireEvent.click(await screen.findByRole('button', { name: 'Save as draft' }));
    await waitFor(() => expect(urls((c) => c.method === 'POST' && c.url === '/api/v1/my-requests/submissions/stock_inquiry')).toHaveLength(1));
  });
});

describe('limited user, edit', () => {
  it('a draft row saves through PUT my-requests/submissions/stock_inquiry/{id}', async () => {
    sources['si-5'] = detail({ id: 'si-5', status: 'draft' });
    mount(LIMITED, { inquiryId: 'si-5' });
    fireEvent.click(await screen.findByRole('button', { name: 'Save as draft' }));
    await waitFor(() => expect(urls((c) => c.method === 'PUT' && c.url === '/api/v1/my-requests/submissions/stock_inquiry/si-5')).toHaveLength(1));
  });

  it('a rejected row is editable (send-back button available)', async () => {
    sources['si-5'] = detail({ id: 'si-5', status: 'rejected', is_draft: true });
    mount(LIMITED, { inquiryId: 'si-5' });
    expect(await screen.findByRole('button', { name: new RegExp(`^${submitVerb('rejected')}`) })).toBeInTheDocument();
  });

  it.each(['pending_purchasing', 'responded', 'resubmitted'])('a %s row offers no save or submit when not revising', async (status) => {
    sources['si-5'] = detail({ id: 'si-5', status, is_draft: false, is_editable: false });
    mount(LIMITED, { inquiryId: 'si-5' });
    await screen.findByPlaceholderText('Code');
    expect(screen.queryByRole('button', { name: 'Save as draft' })).toBeNull();
    expect(screen.queryByRole('button', { name: /^Submit/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /Update Stock Inquiry|Update & Reply/ })).toBeNull();
  });

  it('?revise=1 on a revisable row freezes the requestor picker and Send revision POSTs .../revise', async () => {
    sources['si-5'] = detail({
      id: 'si-5',
      status: 'responded',
      is_draft: false,
      is_editable: false,
      revision: { enabled: true, allowed: true, used: 0, max: 3, remaining: 3, blocked_reason: null },
    });
    mount(LIMITED, { inquiryId: 'si-5' }, '?revise=1');
    await screen.findByPlaceholderText('Code');
    await waitFor(() => expect(screen.getByTestId('requestor-picker').getAttribute('data-disabled')).toBe('true'));
    fireEvent.change(await screen.findByPlaceholderText('Code'), { target: { value: 'NEW-2' } });
    const reason = document.getElementById('revision_reason') ?? screen.getByLabelText(/reason/i);
    fireEvent.change(reason, { target: { value: 'wrong code' } });
    await clickThrough(/Send revision/);
    await waitFor(() => expect(urls((c) => c.method === 'POST' && c.url === '/api/v1/my-requests/submissions/stock_inquiry/si-5/revise')).toHaveLength(1));
    const body = urls((c) => c.url.endsWith('/revise'))[0].body as Record<string, unknown>;
    expect(body).toMatchObject({ reason: 'wrong code', expected_revision_no: 0 });
  });
});

describe('staff user, /new (control, P4-26)', () => {
  it('keeps the purchasing response, shows no draft buttons, and never touches my-requests', async () => {
    mount(STAFF);
    await screen.findByPlaceholderText('Code');
    expect(screen.getByPlaceholderText('For purchasing use')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Save as draft' })).toBeNull();
    expect(screen.queryByRole('button', { name: /^Submit/ })).toBeNull();
    expect(screen.getByRole('button', { name: 'Create Stock Inquiry' })).toBeInTheDocument();
    expect(urls((c) => c.url.startsWith('/api/v1/my-requests/'))).toHaveLength(0);
  });
});
