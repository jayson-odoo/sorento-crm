/**
 * PORTAL-P4-REQUESTS R3b (form parity, PAR-1..7): a LIMITED user (`view_own`, not `view`) creates, edits and VIEWS a
 * Price Tag Request through the PORTAL's own PriceTagRequestForm (app/(auth)/portal/components), every call through
 * `apiFetch` to `/api/v1/my-requests` (the portal's `/api/v1/public/portal/X` is my-requests `X`). Entry points are
 * what the pages render: PriceTagRequestPage (view + edit) and the default export of new/page.tsx (create).
 * Staff (`.view`) keep PriceTagRequestDetail. OwnPriceTagRequest is deleted by this slice.
 *
 * Markers that tell the PORTAL form from OwnPriceTagRequest:
 *   - edit / create: buttons "Save Draft" and "Submit" (Own: "Save as draft"), a "Debtor" picker (portal select id
 *     `debtor`, Own: "Select customer"), and no "Printing:" line;
 *   - view: a "Status:" label row and the gear "Price tag request actions" (Own: no "Status:" text).
 * The portal form's debtor lookup is `lookups/debtors-for-agent` (not `lookups/debtors`).
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { selectOption } from '@/test-utils';

class StubResizeObserver {
  private callback: ResizeObserverCallback;
  constructor(callback: ResizeObserverCallback) {
    this.callback = callback;
  }
  observe() {
    this.callback([{ contentRect: { width: 640, height: 480 } } as ResizeObserverEntry], this as unknown as ResizeObserver);
  }
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as Record<string, unknown>).ResizeObserver = StubResizeObserver;

const state = vi.hoisted(() => ({
  perms: new Set<string>(),
  detail: {} as Record<string, unknown>,
  design: null as Record<string, unknown> | null,
}));
const nav = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn() }));
const pending = vi.hoisted(() => ({ createPendingAction: vi.fn(), cancelPendingAction: vi.fn(), getCurrentPendingAction: vi.fn() }));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: nav.push, replace: nav.replace, refresh: vi.fn(), prefetch: vi.fn(), back: vi.fn() }),
  useSearchParams: () => new URLSearchParams(typeof window === 'undefined' ? '' : window.location.search),
  usePathname: () => '/dealer-kit/price-tag-requests/req-1',
}));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => state.perms.has(slug),
  useHasAnyPermission: (slugs: string[]) => slugs.some((s) => state.perms.has(s)),
  usePermissions: () => ({ permissionSet: state.perms, permissions: [...state.perms], isLoading: false, isError: false }),
}));
vi.mock('@/components/common/container', () => ({ Container: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), dismiss: vi.fn(), info: vi.fn(), warning: vi.fn() } }));
vi.mock('@/components/common/deferredToast', () => ({ deferredToast: vi.fn(() => 't'), dismissDeferredToast: vi.fn() }));
vi.mock('@/services/pendingActionService', () => pending);
vi.mock('@/components/common/DetailActionsMenu', () => ({
  DetailActionsMenu: ({ children, ariaLabel }: { children: React.ReactNode; ariaLabel?: string }) => (
    <div data-testid="gear-menu" aria-label={ariaLabel}>{children}</div>
  ),
}));
vi.mock('@/components/ui/dropdown-menu', () => ({
  DropdownMenuItem: ({ children, onSelect, disabled }: { children: React.ReactNode; onSelect?: (e: { preventDefault: () => void }) => void; disabled?: boolean }) => (
    <button role="menuitem" disabled={disabled} onClick={() => onSelect?.({ preventDefault: () => {} })}>{children}</button>
  ),
}));
vi.mock('@/components/common/AttachmentPreviewModal', () => ({ __esModule: true, default: () => null }));
vi.mock('@/lib/dealer-kit/fonts', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/dealer-kit/fonts')>();
  return { ...actual, ensureFontsLoaded: vi.fn(async () => {}), ensureSeedFontsLoaded: vi.fn(async () => {}) };
});
vi.mock('@/lib/save-blob', async (importOriginal) => ({ ...(await importOriginal<Record<string, unknown>>()), saveBlobAs: vi.fn() }));
// A native select for the debtor picker (the portal's own suites do the same): `selectOption('Debtor', code)`.
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    id?: string;
    value: string;
    onChange: (v: string) => void;
    onOptionChange?: (o: { value: string; label: string; description?: string } | null) => void;
    options?: { value: string; label: string; description?: string }[];
    fetchOptions?: (q: string) => Promise<{ value: string; label: string; description?: string }[]>;
    placeholder?: string;
  }) => {
    const [fetched, setFetched] = React.useState<{ value: string; label: string; description?: string }[]>([]);
    React.useEffect(() => {
      if (props.fetchOptions) void props.fetchOptions('').then(setFetched);
    }, [props.fetchOptions]);
    const options = props.options ?? fetched;
    return (
      <select
        aria-label={props.id === 'debtor' ? 'Debtor' : (props.placeholder ?? '')}
        value={props.value}
        onChange={(e) => {
          props.onChange(e.target.value);
          props.onOptionChange?.(options.find((o) => o.value === e.target.value) ?? null);
        }}
      >
        <option value="">{props.placeholder ?? ''}</option>
        {options.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    );
  },
}));

interface Call { url: string; method: string; body: unknown }
const calls: Call[] = [];
const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status, headers: { 'content-type': 'application/json' } });
const ME = { contact_id: 'c1', space_id: 'sp1', name: 'Ann Sales', phone_number: '60123456789', expires_at: '2030-01-01T00:00:00Z' };
const DEBTOR_ROWS = [
  // no debtor_code: the form sends customer_code
  { customer_id: 'cu-1', customer_code: 'ZZT-CUST-1', customer_name: 'ZZT Customer One', debtor_code: null, debtor_name: null },
  // debtor_code wins over customer_code
  { customer_id: 'cu-2', customer_code: 'ZZT-CUST-2', customer_name: 'ZZT Customer Two', debtor_code: 'ZZT-DEB-2', debtor_name: 'ZZT Debtor Two' },
];
const MINE = '/api/v1/my-requests/submissions/price_tag_request';
const apiFetch = vi.fn(async (url: string, init?: RequestInit) => {
  const method = (init?.method ?? 'GET').toUpperCase();
  let body: unknown = init?.body;
  if (typeof body === 'string') {
    try { body = JSON.parse(body); } catch { /* keep */ }
  }
  calls.push({ url, method, body });
  const path = url.split('?')[0];
  if (path === '/api/v1/my-requests/me') return json(ME);
  if (path === '/api/v1/my-requests/lookups/debtors-for-agent') return json(DEBTOR_ROWS);
  if (path === '/api/v1/my-requests/lookups/price-tag-items') return json([{ kind: 'product', id: 'p-1', code: 'SNK-1', name: 'ZZT Sink' }]);
  if (path.startsWith('/api/v1/my-requests/lookups/product-combos/')) return json({ host_guarded: false, combos: [] });
  if (path === '/api/v1/my-requests/lookups/line-pricing') return json([]);
  if (path.startsWith('/api/v1/my-requests/lookups/')) return json([]);
  if (path === '/api/v1/my-requests/attachments' && method === 'POST') {
    return json({ link_id: 'l1', attachment_id: 'a1', filename: 'f.pdf', size: 3, url: 'https://cdn/f.pdf', uploader_kind: 'contact', can_unlink: true });
  }
  if (path.endsWith('/neighbours')) return json({ prev_id: null, next_id: null, position: 1, total: 1 });
  if (path.endsWith('/revisions')) return json({ items: [] });
  if (path.endsWith('/comments')) return json({ items: [] });
  if (path.endsWith('/review-comments')) return json([]);
  if (/\/submissions\/price_tag_request\/[^/]+\/design$/.test(path)) return state.design ? json(state.design) : json({ detail: 'none' }, 404);
  if (path.endsWith('/download')) return new Response(new Blob(['%PDF']), { status: 200, headers: { 'content-type': 'application/pdf' } });
  if (path.endsWith('/submit')) return json({ ...state.detail, status: 'new', portal_draft_at: null });
  if (path.endsWith('/approve')) return json({ status: 'approved' });
  if (path.endsWith('/collect')) return json({ status: 'collected' });
  if (path.endsWith('/export')) return json({ status: 'pending' });
  if (path.endsWith('/request-changes')) return json({ status: 'changes_requested', round: 1, comments: [] });
  if (path === '/api/v1/dealer-kit/price-tag-requests/req-1' && method === 'GET') return json(state.detail);
  if (path.startsWith('/api/v1/dealer-kit/')) return json([]);
  if (path === MINE && method === 'POST') return json({ ...state.detail, id: 'new-1' });
  if (path.startsWith(`${MINE}/`)) {
    if (method === 'DELETE') return new Response(null, { status: 204 });
    return json(state.detail);
  }
  return json([]);
});
vi.mock('@/lib/api', () => ({ apiFetch: (...a: [string, RequestInit?]) => apiFetch(...a) }));

import PriceTagRequestPage from './PriceTagRequestPage';
import NewPriceTagRequestPage from '../new/page';

const P = 'dealer_kit.price_tag_requests';
const LIMITED = [`${P}.view_own`, `${P}.create`];
const STAFF = [`${P}.view`, `${P}.process`];
const LIST = '/dealer-kit/price-tag-requests';

const DESIGN = {
  page_id: 'page-1', version: 2, source: 'version',
  doc: {
    kind: 'tag_sheet', imposition: { page_width_mm: 210, page_height_mm: 297 },
    sheets: [{ id: 'sheet-1', tags: [{ id: 'tag-1', request_tag_id: 'l-1', x_mm: 20, y_mm: 30, width_mm: 80, height_mm: 40, layers: [] }] }],
  },
  lines: [], assets: {}, images: {}, fonts: [],
};

function detail(over: Record<string, unknown> = {}) {
  return {
    id: 'req-1', contact_id: 'ct-1', doc_number: 'PT-202610-0001', status: 'new', portal_draft_at: '2026-10-01T01:00:00',
    debtor_code: 'ZZT-DEB-2', debtor_name: 'ZZT Debtor Two', needed_by_date: '2030-01-15', notes: null, price_mode: 'list',
    print_by: 'self', created_at: '2026-10-01T01:00:00', line_count: 1, revision_no: 0, attachments: [], review_round: 1,
    is_editable: true, has_completed_export: false, latest_export_status: null,
    revision: { enabled: true, allowed: false, used: 0, max: 3, remaining: 3, blocked_reason: null },
    lines: [{
      id: 'l-1', line_type: 'product', product_id: 'p-1', product_set_id: null, name: 'ZZT Sink', code: 'SNK-1',
      show_promo_price: false, quantity: 2, included_accessories: null, remarks: null, sort_order: 0,
      list_price: 100, sell_price: 100, parts: [], package_warning: null, tags: [{ id: 'l-1', label: '1a', quantity: 2 }],
    }],
    ...over,
  };
}
const SUBMITTED = { portal_draft_at: null, is_editable: false };

const where = (pred: (c: Call) => boolean) => calls.filter(pred);
const portalCalls = () => where((c) => c.url.startsWith('/api/v1/public/portal'));
const staffApi = () => where((c) => c.url.startsWith('/api/v1/dealer-kit/price-tag-requests'));
const posted = (suffix: string) => where((c) => c.method === 'POST' && c.url === `${MINE}/req-1/${suffix}`);
const pushed = () => nav.push.mock.calls.map((a) => String(a[0]));

function wrap(node: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
}
function mountNew(slugs = LIMITED, search = '') {
  state.perms = new Set(slugs);
  window.history.replaceState({}, '', `${LIST}/new${search}`);
  return wrap(<NewPriceTagRequestPage />);
}
function mountPage(slugs: string[], over: Record<string, unknown> = {}) {
  state.perms = new Set(slugs);
  state.detail = detail(over);
  window.history.replaceState({}, '', `${LIST}/req-1`);
  return wrap(<PriceTagRequestPage requestId="req-1" />);
}

/** Same gesture the portal's own suite uses: click the tag, type the comment, Add. */
async function placePin(text: string) {
  const hit = await screen.findByTestId('pin-hit-l-1');
  hit.getBoundingClientRect = () => ({ left: 100, top: 200, width: 200, height: 100, right: 300, bottom: 300 }) as DOMRect;
  fireEvent.pointerDown(hit, { clientX: 150, clientY: 250 });
  fireEvent.pointerUp(hit, { clientX: 150, clientY: 250 });
  const editor = await screen.findByTestId('pin-comment-editor');
  fireEvent.change(within(editor).getByRole('textbox'), { target: { value: text } });
  fireEvent.click(within(editor).getByRole('button', { name: 'Add' }));
}

/** The portal form, not OwnPriceTagRequest: Save Draft / Submit buttons and the portal's Debtor picker. */
async function expectPortalEditForm() {
  expect(await screen.findByRole('button', { name: 'Save Draft' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Submit' })).toBeInTheDocument();
  expect(screen.getByLabelText('Debtor')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Save as draft' })).toBeNull();
  expect(screen.queryByText(/^Printing:/)).toBeNull();
}

beforeEach(() => {
  cleanup();
  calls.length = 0;
  vi.clearAllMocks();
  state.design = DESIGN;
  state.detail = detail();
  pending.getCurrentPendingAction.mockResolvedValue({ pending: null, last_outcome: null });
  (URL as unknown as Record<string, unknown>).createObjectURL = vi.fn(() => 'blob:x');
  (URL as unknown as Record<string, unknown>).revokeObjectURL = vi.fn();
});
afterEach(cleanup);

describe('limited user, New Price Tag Request renders the portal form', () => {
  it('is the portal form (Save Draft / Submit / Debtor), reading its lookups through my-requests only', async () => {
    mountNew();
    await expectPortalEditForm();
    await waitFor(() => expect(where((c) => c.url.startsWith('/api/v1/my-requests/lookups/debtors-for-agent')).length).toBeGreaterThan(0));
    expect(calls.length).toBeGreaterThan(0);
    expect(calls.every((c) => c.url.startsWith('/api/v1/my-requests'))).toBe(true);
    expect(portalCalls()).toHaveLength(0);
    expect(staffApi()).toHaveLength(0);
  });

  it('Save Draft with a customer that has no debtor_code POSTs customer_code and print_by self, then pushes the CRM list', async () => {
    mountNew();
    await expectPortalEditForm();
    await selectOption('Debtor', 'ZZT-CUST-1');
    fireEvent.click(screen.getByRole('button', { name: 'Save Draft' }));
    await waitFor(() => expect(where((c) => c.method === 'POST' && c.url === MINE)).toHaveLength(1));
    expect(where((c) => c.method === 'POST' && c.url === MINE)[0].body).toEqual({
      debtor_code: 'ZZT-CUST-1', debtor_name: 'ZZT Customer One', needed_by_date: null, notes: null,
      price_mode: 'list', print_by: 'self', lines: [],
    });
    await waitFor(() => expect(pushed().some((p) => p === LIST || p.startsWith(`${LIST}?`) || p.startsWith(`${LIST}/`))).toBe(true));
    expect(pushed().every((p) => !p.startsWith('/portal'))).toBe(true);
    expect(portalCalls()).toHaveLength(0);
    expect(staffApi()).toHaveLength(0);
  });

  it('Save Draft with a customer that has a debtor_code POSTs the debtor_code (debtor_code ?? customer_code)', async () => {
    mountNew();
    await expectPortalEditForm();
    await selectOption('Debtor', 'ZZT-DEB-2');
    fireEvent.click(screen.getByRole('button', { name: 'Save Draft' }));
    await waitFor(() => expect(where((c) => c.method === 'POST' && c.url === MINE)).toHaveLength(1));
    expect(where((c) => c.method === 'POST' && c.url === MINE)[0].body).toMatchObject({
      debtor_code: 'ZZT-DEB-2', debtor_name: 'ZZT Debtor Two', print_by: 'self', price_mode: 'list',
    });
  });

  it('?from=<id> on New loads that request through my-requests', async () => {
    mountNew(LIMITED, '?from=req-0');
    await expectPortalEditForm();
    await waitFor(() => expect(where((c) => c.method === 'GET' && c.url === `${MINE}/req-0`).length).toBeGreaterThan(0));
    expect(portalCalls()).toHaveLength(0);
    expect(staffApi()).toHaveLength(0);
  });
});

describe('limited user, edit of a draft', () => {
  it('GETs my-requests/.../<id>, shows the portal form, saves with PUT, never the staff API or /public/portal', async () => {
    mountPage(LIMITED);
    await expectPortalEditForm();
    expect(where((c) => c.method === 'GET' && c.url === `${MINE}/req-1`).length).toBeGreaterThan(0);
    await waitFor(() => expect(where((c) => c.url.startsWith(`${MINE}/req-1/neighbours`)).length).toBeGreaterThan(0));
    fireEvent.click(screen.getByRole('button', { name: 'Save Draft' }));
    await waitFor(() => expect(where((c) => c.method === 'PUT' && c.url === `${MINE}/req-1`)).toHaveLength(1));
    expect(where((c) => c.method === 'PUT')[0].body).toMatchObject({ debtor_code: 'ZZT-DEB-2', print_by: 'self', price_mode: 'list' });
    await waitFor(() => expect(pushed().some((p) => p.startsWith(LIST))).toBe(true));
    expect(pushed().every((p) => !p.startsWith('/portal'))).toBe(true);
    expect(staffApi()).toHaveLength(0);
    expect(portalCalls()).toHaveLength(0);
  });

  it('Submit PUTs then POSTs .../<id>/submit and pushes the CRM list (never /portal)', async () => {
    mountPage(LIMITED);
    fireEvent.click(await screen.findByRole('button', { name: 'Submit' }));
    await waitFor(() => expect(posted('submit')).toHaveLength(1));
    await waitFor(() => expect(pushed().some((p) => p.startsWith(LIST))).toBe(true));
    expect(pushed().every((p) => !p.startsWith('/portal'))).toBe(true);
    expect(staffApi()).toHaveLength(0);
    expect(portalCalls()).toHaveLength(0);
  });
});

describe('limited user, view of a submitted request', () => {
  it('renders the portal read-only view (Status:, gear) loaded from my-requests, no staff detail, no /public/portal', async () => {
    mountPage(LIMITED, SUBMITTED);
    expect(await screen.findByText('Status:')).toBeInTheDocument();
    expect(screen.getByLabelText('Price tag request actions')).toBeInTheDocument();
    expect(screen.queryByText(/^Printing:/)).toBeNull();
    expect(screen.queryByRole('button', { name: 'Save Draft' })).toBeNull();
    expect(where((c) => c.method === 'GET' && c.url === `${MINE}/req-1`).length).toBeGreaterThan(0);
    await waitFor(() => expect(where((c) => c.url.startsWith(`${MINE}/req-1/neighbours`)).length).toBeGreaterThan(0));
    expect(staffApi()).toHaveLength(0);
    expect(portalCalls()).toHaveLength(0);
  });

  it('Duplicate in the gear pushes the CRM New page with ?from=<id>', async () => {
    mountPage(LIMITED, SUBMITTED);
    fireEvent.click(await screen.findByRole('menuitem', { name: /Duplicate/ }));
    await waitFor(() => expect(pushed()).toContain(`${LIST}/new?from=req-1`));
    expect(pushed().every((p) => !p.startsWith('/portal'))).toBe(true);
  });

  it('ready for collection: Mark collected POSTs .../<id>/collect through my-requests', async () => {
    mountPage(LIMITED, { ...SUBMITTED, status: 'ready_for_collection', ready_for_collection_at: '2026-10-05T01:00:00' });
    fireEvent.click(await screen.findByTestId('portal-mark-collected'));
    await waitFor(() => expect(posted('collect')).toHaveLength(1));
    expect(staffApi().filter((c) => c.method !== 'GET')).toHaveLength(0);
    expect(portalCalls()).toHaveLength(0);
  });

  it('Download PDF in the gear (export ready) GETs .../<id>/download through my-requests', async () => {
    mountPage(LIMITED, { ...SUBMITTED, status: 'approved', has_completed_export: true, latest_export_status: 'ready' });
    fireEvent.click(await screen.findByRole('menuitem', { name: /Download PDF/ }));
    await waitFor(() => expect(where((c) => c.method === 'GET' && c.url.split('?')[0] === `${MINE}/req-1/download`).length).toBeGreaterThan(0));
    expect(portalCalls()).toHaveLength(0);
  });

  it('PDF not exported yet: the gear item queues POST .../<id>/export through my-requests', async () => {
    mountPage(LIMITED, { ...SUBMITTED, status: 'approved', has_completed_export: false, latest_export_status: null });
    fireEvent.click(await screen.findByRole('menuitem', { name: /Download PDF/ }));
    await waitFor(() => expect(posted('export')).toHaveLength(1));
    expect(portalCalls()).toHaveLength(0);
  });
});

describe('limited user, proof review on a request awaiting approval', () => {
  const PROOF = { ...SUBMITTED, status: 'proof_ready' };

  it('reads the design and the review rounds through my-requests', async () => {
    mountPage(LIMITED, PROOF);
    expect(await screen.findByTestId('pin-hit-l-1')).toBeTruthy();
    expect(where((c) => c.method === 'GET' && c.url.split('?')[0] === `${MINE}/req-1/design`).length).toBeGreaterThan(0);
    await waitFor(() => expect(where((c) => c.method === 'GET' && c.url.split('?')[0] === `${MINE}/req-1/review-comments`).length).toBeGreaterThan(0));
    expect(portalCalls()).toHaveLength(0);
    expect(staffApi()).toHaveLength(0);
  });

  it('Approve POSTs .../<id>/approve through my-requests, then pushes the CRM list', async () => {
    mountPage(LIMITED, PROOF);
    await screen.findByTestId('pin-hit-l-1');
    fireEvent.click((await screen.findAllByRole('button', { name: /^Approve/ }))[0]);
    await waitFor(() => expect(posted('approve')).toHaveLength(1));
    await waitFor(() => expect(pushed().some((p) => p.startsWith(LIST))).toBe(true));
    expect(pushed().every((p) => !p.startsWith('/portal'))).toBe(true);
  });

  it('Request changes (a pin and a note) POSTs ONE .../<id>/request-changes with the portal body, then pushes the CRM list', async () => {
    mountPage(LIMITED, PROOF);
    await placePin('Make the price bigger');
    fireEvent.change(await screen.findByLabelText(/Anything else \(optional\)/), { target: { value: 'Too busy' } });
    fireEvent.click(await screen.findByTestId('send-change-requests'));
    await waitFor(() => expect(posted('request-changes')).toHaveLength(1));
    const body = posted('request-changes')[0].body as { comments: Array<Record<string, unknown>>; note?: string };
    expect(body.comments).toHaveLength(1);
    expect(body.comments[0]).toMatchObject({ tag_id: 'l-1', body: 'Make the price bigger' });
    expect(body.note).toBe('Too busy');
    await waitFor(() => expect(pushed().some((p) => p.startsWith(LIST))).toBe(true));
    expect(pushed().every((p) => !p.startsWith('/portal'))).toBe(true);
  });
});

describe('limited user, deletes inside the portal form are D7 deferred (never an immediate DELETE)', () => {
  it('Delete draft parks my_request.delete for price_tag_request, with no confirm dialog', async () => {
    pending.createPendingAction.mockResolvedValue({
      id: 'pa-1', action_key: 'my_request.delete', entity_type: 'price_tag_request', entity_id: 'req-1',
      commit_at: new Date(Date.now() + 10_000).toISOString().replace(/\.\d+Z$/, ''), window_seconds: 10,
    });
    mountPage(LIMITED);
    await expectPortalEditForm();
    fireEvent.click(await screen.findByRole('button', { name: /Delete/i }));
    await waitFor(() =>
      expect(pending.createPendingAction).toHaveBeenCalledWith(
        expect.objectContaining({ actionKey: 'my_request.delete', entityType: 'price_tag_request', entityId: 'req-1' }),
      ),
    );
    expect(screen.queryByRole('alertdialog')).toBeNull();
    expect(screen.queryByText('Delete this draft?')).toBeNull();
    expect(where((c) => c.method === 'DELETE')).toHaveLength(0);
  });

  it('removing an own uploaded attachment parks my_request_attachment.unlink, no immediate DELETE', async () => {
    pending.createPendingAction.mockResolvedValue({
      id: 'pa-2', action_key: 'my_request_attachment.unlink', entity_type: 'my_request_attachment', entity_id: 'link-1',
      commit_at: new Date(Date.now() + 5_000).toISOString().replace(/\.\d+Z$/, ''), window_seconds: 5,
    });
    mountPage(LIMITED, {
      attachments: [{ link_id: 'link-1', attachment_id: 'att-1', filename: 'mine.pdf', size: 3, url: 'https://cdn/mine.pdf', uploader_kind: 'contact', can_unlink: true }],
    });
    await expectPortalEditForm();
    fireEvent.click(await screen.findByRole('button', { name: 'Remove attachment' }));
    await waitFor(() =>
      expect(pending.createPendingAction).toHaveBeenCalledWith(
        expect.objectContaining({ actionKey: 'my_request_attachment.unlink', entityType: 'my_request_attachment', entityId: 'link-1' }),
      ),
    );
    expect(where((c) => c.method === 'DELETE')).toHaveLength(0);
  });
});

describe('staff keep marketing\'s Price Tag Request page', () => {
  it('a view holder gets PriceTagRequestDetail: no portal form, nothing through my-requests', async () => {
    mountPage(STAFF, SUBMITTED);
    expect(await screen.findByRole('heading', { level: 1, name: 'PT-202610-0001' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Save Draft' })).toBeNull();
    expect(screen.queryByText('Status:')).toBeNull();
    await waitFor(() => expect(staffApi().length).toBeGreaterThan(0));
    expect(where((c) => c.url.startsWith('/api/v1/my-requests'))).toHaveLength(0);
  });
});
