/**
 * PORTAL-P4-REQUESTS S7 (v1.2, Q8): the staff Price Tag Request page for a LIMITED user (`.view_own` + `.create`,
 * never `.view` / `.process`) and for staff (control). Asserted at the HTTP seam (`apiFetch`), so it holds however
 * the coder splits hooks.
 *
 * Convention assumed (the repo already uses it in SalesOrderDetail / PurchaseOrderDetail): Edit = the SAME
 * detail layout with `?edit=1`, fields become inputs in place; Create = `/dealer-kit/price-tag-requests/new`.
 * Both pages are mounted through their route files (`new/page.tsx`, `[id]/page.tsx`).
 *
 *  - view: only the portal action set (Edit / Delete for a draft, Submit, Approve proof, Request changes,
 *    Mark collected, Revise when the server allows it, Duplicate), every write through /api/v1/my-requests
 *  - hidden for a limited user: Claim, Design tags / View design, Void, Export PDF, Edit request, line price
 *  - edit / new: Save as draft and Submit through my-requests, the debtor picker is the my-requests lookup
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const state = vi.hoisted(() => ({
  perms: new Set<string>(),
  search: '',
  detail: {} as Record<string, unknown>,
  revision: { enabled: true, allowed: false, used: 0, max: 3, remaining: 3, blocked_reason: null } as Record<string, unknown>,
}));
const nav = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn() }));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: nav.push, replace: nav.replace, refresh: vi.fn(), prefetch: vi.fn(), back: vi.fn() }),
  useSearchParams: () => new URLSearchParams(state.search),
  usePathname: () => '/dealer-kit/price-tag-requests/req-1',
}));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => state.perms.has(slug),
  useHasAnyPermission: (slugs: string[]) => slugs.some((s) => state.perms.has(s)),
  usePermissions: () => ({ permissionSet: state.perms, permissions: [...state.perms], isLoading: false, isError: false }),
}));
vi.mock('@/components/common/container', () => ({ Container: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), dismiss: vi.fn(), info: vi.fn(), warning: vi.fn() } }));
vi.mock('@/hooks/useDeferredAction', () => ({
  useDeferredAction: () => ({ pending: null, isPending: false, isBlocked: false, start: vi.fn(), cancel: vi.fn(), countdown: null }),
}));
vi.mock('@/components/common/DetailActionsMenu', () => ({
  DetailActionsMenu: ({ children }: { children: React.ReactNode }) => <div data-testid="gear-menu">{children}</div>,
}));
vi.mock('@/components/ui/dropdown-menu', () => ({
  DropdownMenuItem: ({ children, onSelect }: { children: React.ReactNode; onSelect?: (e: { preventDefault: () => void }) => void }) => (
    <button role="menuitem" onClick={() => onSelect?.({ preventDefault: () => {} })}>{children}</button>
  ),
}));
vi.mock('@/components/common/AttachmentPreviewModal', () => ({ __esModule: true, default: () => null }));

const calls: Array<{ url: string; method: string; body: unknown }> = [];
const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status, headers: { 'content-type': 'application/json' } });
const apiFetch = vi.fn(async (url: string, init?: RequestInit) => {
  const method = (init?.method ?? 'GET').toUpperCase();
  let body: unknown = init?.body;
  if (typeof body === 'string') {
    try { body = JSON.parse(body); } catch { /* keep */ }
  }
  calls.push({ url, method, body });
  const path = url.split('?')[0];
  if (/\/api\/v1\/dealer-kit\/price-tag-requests\/req-1$/.test(path) && method === 'GET') return json(state.detail);
  if (/\/api\/v1\/my-requests\/submissions\/price_tag_request\/req-1$/.test(path) && method === 'GET') {
    return json({ ...state.detail, revision: state.revision });
  }
  if (path.startsWith('/api/v1/my-requests/submissions/price_tag_request') && method !== 'GET') return json({ ...state.detail, id: 'req-1' });
  if (path.endsWith('/design')) return json({ detail: 'none' }, 404);
  if (path.includes('/lookups/debtors-for-agent') || path.endsWith('/debtors')) {
    return json([{ customer_id: 'c-1', customer_code: 'D-001', customer_name: 'ZZT Dealer', debtor_code: 'D-001', debtor_name: 'ZZT Dealer', source: 'customer' }]);
  }
  if (path.includes('/lookups/product-combos/')) return json({ host_guarded: false, combos: [] });
  return json([]);
});
vi.mock('@/lib/api', () => ({ apiFetch: (...a: [string, RequestInit?]) => apiFetch(...a) }));

import DetailPage from '../[id]/page';

const LIMITED = ['dealer_kit.price_tag_requests.view_own', 'dealer_kit.price_tag_requests.create'];
const STAFF = ['dealer_kit.price_tag_requests.view', 'dealer_kit.price_tag_requests.process'];
const MINE = '/api/v1/my-requests/submissions/price_tag_request';
const STAFF_BASE = '/api/v1/dealer-kit/price-tag-requests';
const STAFF_WRITE = (c: { url: string; method: string }) => c.url.startsWith(STAFF_BASE) && c.method !== 'GET';

function detail(over: Record<string, unknown> = {}) {
  return {
    id: 'req-1', contact_id: 'ct-1', doc_number: 'PT-202610-0001', status: 'new', portal_draft_at: '2026-10-01T01:00:00',
    debtor_code: 'D-001', debtor_name: 'ZZT Dealer', needed_by_date: null, notes: null, price_mode: 'list',
    print_by: 'office', created_at: '2026-10-01T01:00:00', assigned_to_id: null, assigned_to_name: null,
    contact_name: 'Sales Sam', line_count: 1, data_changed_tag_count: 0, revision_no: 0, attachments: [], review_round: 0,
    lines: [{
      id: 'l-1', line_type: 'product', product_id: 'p-1', product_set_id: null, name: 'ZZT Sink', code: 'SNK-1',
      show_promo_price: false, quantity: 2, included_accessories: null, remarks: null, sort_order: 0,
      list_price: 100, sell_price: 100, parts: [], package_warning: null, tags: [],
    }],
    ...over,
  };
}

async function mountDetail(slugs: string[], over: Record<string, unknown> = {}, search = '') {
  state.perms = new Set(slugs);
  state.search = search;
  state.detail = detail(over);
  const el = await (DetailPage as unknown as (p: unknown) => Promise<React.ReactElement> | React.ReactElement)({
    params: Promise.resolve({ id: 'req-1' }),
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{el}</QueryClientProvider>);
}

const posted = (suffix: string) => calls.filter((c) => c.method === 'POST' && c.url === `${MINE}/req-1/${suffix}`);

beforeEach(() => {
  calls.length = 0;
  nav.push.mockClear();
  nav.replace.mockClear();
  state.revision = { enabled: true, allowed: false, used: 0, max: 3, remaining: 3, blocked_reason: null };
});
afterEach(cleanup);

describe('Price Tag Request page, limited user, view', () => {
  it('Submit POSTs through my-requests and never a staff write route', async () => {
    await mountDetail(LIMITED);
    fireEvent.click(await screen.findByText('Submit'));
    await waitFor(() => expect(posted('submit')).toHaveLength(1));
    expect(calls.filter(STAFF_WRITE)).toHaveLength(0);
  });

  it('proof ready: Approve proof POSTs .../approve, Request changes is offered, the designer is not', async () => {
    await mountDetail(LIMITED, { portal_draft_at: null, status: 'proof_ready' });
    fireEvent.click((await screen.findAllByRole('button', { name: /^Approve/ }))[0]);
    await waitFor(() => expect(posted('approve')).toHaveLength(1));
    expect(screen.getByLabelText(/Anything else \(optional\)/)).toBeTruthy();
    expect(screen.queryByText('View design')).toBeNull();
    expect(screen.queryByText('Design tags')).toBeNull();
    expect(calls.filter(STAFF_WRITE)).toHaveLength(0);
  });

  it('ready for collection: Mark collected POSTs .../collect, not the staff transition', async () => {
    await mountDetail(LIMITED, { portal_draft_at: null, status: 'ready_for_collection', print_by: 'office' });
    fireEvent.click(await screen.findByText('Mark collected'));
    await waitFor(() => expect(posted('collect')).toHaveLength(1));
    expect(calls.filter((c) => c.url.endsWith('/transition'))).toHaveLength(0);
  });

});

describe('Price Tag Request page, page Back (owner hand test 2 point 4)', () => {
  it('a limited user sees no page-level Back link', async () => {
    await mountDetail(LIMITED);
    await screen.findByText('Submit');
    expect(screen.queryByText(/^Back to /)).toBeNull();
    expect(screen.queryByRole('link', { name: /^Back to / })).toBeNull();
  });

  it('staff keep the page Back link (pin)', async () => {
    await mountDetail(STAFF, { portal_draft_at: null, status: 'new' });
    await screen.findByText('Claim');
    expect(screen.getByText('Back to price tag requests')).toBeTruthy();
  });
});

describe('Price Tag Request page, limited user, edit and create', () => {
  it('Submit in edit mode ends in POST .../submit through my-requests', async () => {
    await mountDetail(LIMITED, {}, 'edit=1');
    fireEvent.click(await screen.findByRole('button', { name: 'Submit' }));
    await waitFor(() => expect(posted('submit')).toHaveLength(1));
    expect(calls.filter(STAFF_WRITE)).toHaveLength(0);
  });

});

describe('Price Tag Request page, staff user (control)', () => {
  it('a process holder still sees Claim on an unclaimed submitted request and none of the salesperson actions', async () => {
    await mountDetail(STAFF, { portal_draft_at: null, status: 'new' });
    expect(await screen.findByText('Claim')).toBeTruthy();
    for (const label of ['Submit', 'Approve proof', 'Duplicate', 'Delete']) expect(screen.queryByText(label), label).toBeNull();
    expect(calls.filter((c) => c.url.startsWith('/api/v1/my-requests'))).toHaveLength(0);
  });
});
