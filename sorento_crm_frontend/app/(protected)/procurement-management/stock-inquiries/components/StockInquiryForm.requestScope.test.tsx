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
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
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

beforeEach(() => {
  cleanup();
  calls.length = 0;
  sources = {};
  vi.clearAllMocks();
});

// PORTAL-P4-REQUESTS R1: a limited user now gets the portal's own form; its cases live in StockInquiry.portalForm.test.tsx and the portal's own SubmissionForm tests.



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
