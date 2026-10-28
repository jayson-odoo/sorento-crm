/**
 * PORTAL-P4-REQUESTS S7b (red): proof view + pinned change requests on the CRM price tag request page
 * for a LIMITED user (`view_own`, never `view`). The CRM reuses the portal's own review UI - the shared
 * `DesignViewer` with `DesignPinLayer` pins, the numbered draft rail, the `send-change-requests` button - by
 * moving the portal's private `DesignSection` (PriceTagRequestForm.tsx) somewhere both can import. Asserted at
 * the HTTP seam (`apiFetch`), with the portal's own test ids (`pin-hit-<tag id>`, `send-change-requests`).
 *
 *  a. proof_ready: GET .../my-requests/submissions/price_tag_request/{id}/design is read and the viewer renders
 *  b. Request changes = pins: ONE POST .../request-changes with { comments:[{tag_id,x,y,w,h,body}], note? }
 *     (portal's ChangeRequestPayload), no plain-note dialog
 *  d. staff control: no viewer, no pins, nothing through my-requests
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

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
  search: '',
  detail: {} as Record<string, unknown>,
  design: null as Record<string, unknown> | null,
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
vi.mock('@/lib/dealer-kit/fonts', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/dealer-kit/fonts')>();
  return { ...actual, ensureFontsLoaded: vi.fn(async () => {}), ensureSeedFontsLoaded: vi.fn(async () => {}) };
});

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
  if (/\/api\/v1\/my-requests\/submissions\/price_tag_request\/req-1$/.test(path) && method === 'GET') return json(state.detail);
  if (/\/my-requests\/submissions\/price_tag_request\/req-1\/design$/.test(path)) {
    return state.design ? json(state.design) : json({ detail: 'none' }, 404);
  }
  if (path.endsWith('/request-changes')) return json({ status: 'changes_requested', round: 1, comments: [] });
  if (path.includes('/submissions/price_tag_request') && method !== 'GET') return json({ ...state.detail, id: 'req-1' });
  return json([]);
});
vi.mock('@/lib/api', () => ({ apiFetch: (...a: [string, RequestInit?]) => apiFetch(...a) }));

import PriceTagRequestPage from './PriceTagRequestPage';

const LIMITED = ['dealer_kit.price_tag_requests.view_own', 'dealer_kit.price_tag_requests.create'];
const STAFF = ['dealer_kit.price_tag_requests.view', 'dealer_kit.price_tag_requests.process'];
const MINE = '/api/v1/my-requests/submissions/price_tag_request';

const DESIGN = {
  page_id: 'page-1',
  version: 2,
  source: 'version',
  doc: {
    kind: 'tag_sheet',
    imposition: { page_width_mm: 210, page_height_mm: 297 },
    sheets: [{ id: 'sheet-1', tags: [{ id: 'tag-1', request_tag_id: 'l-1', x_mm: 20, y_mm: 30, width_mm: 80, height_mm: 40, layers: [] }] }],
  },
  lines: [],
  assets: {},
  images: {},
  fonts: [],
};

function detail(over: Record<string, unknown> = {}) {
  return {
    id: 'req-1', contact_id: 'ct-1', doc_number: 'PT-202610-0001', status: 'proof_ready', portal_draft_at: null,
    debtor_code: 'D-001', debtor_name: 'ZZT Dealer', needed_by_date: null, notes: null, price_mode: 'list',
    print_by: 'self', created_at: '2026-10-01T01:00:00', assigned_to_id: null, assigned_to_name: null,
    contact_name: 'Sales Sam', line_count: 1, data_changed_tag_count: 0, revision_no: 0, attachments: [], review_round: 1,
    revision: { enabled: true, allowed: false, used: 0, max: 3, remaining: 3, blocked_reason: null },
    lines: [{
      id: 'l-1', line_type: 'product', product_id: 'p-1', product_set_id: null, name: 'ZZT Sink', code: 'SNK-1',
      show_promo_price: false, quantity: 2, included_accessories: null, remarks: null, sort_order: 0,
      list_price: 100, sell_price: 100, parts: [], package_warning: null,
      tags: [{ id: 'l-1', label: '1a', quantity: 2 }],
    }],
    ...over,
  };
}

function mount(slugs: string[], over: Record<string, unknown> = {}) {
  state.perms = new Set(slugs);
  state.search = '';
  state.detail = detail(over);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <PriceTagRequestPage requestId="req-1" />
    </QueryClientProvider>,
  );
}

/** Same gesture the portal's own suite uses: click the tag, type the comment, Add. */
async function placePin(body: string) {
  const hit = await screen.findByTestId('pin-hit-l-1');
  hit.getBoundingClientRect = () => ({ left: 100, top: 200, width: 200, height: 100, right: 300, bottom: 300 }) as DOMRect;
  fireEvent.pointerDown(hit, { clientX: 150, clientY: 250 });
  fireEvent.pointerUp(hit, { clientX: 150, clientY: 250 });
  const editor = await screen.findByTestId('pin-comment-editor');
  fireEvent.change(within(editor).getByRole('textbox'), { target: { value: body } });
  fireEvent.click(within(editor).getByRole('button', { name: 'Add' }));
}

const posted = (suffix: string) => calls.filter((c) => c.method === 'POST' && c.url === `${MINE}/req-1/${suffix}`);

beforeEach(() => {
  calls.length = 0;
  nav.push.mockClear();
  state.design = DESIGN;
});
afterEach(cleanup);

describe('limited user, proof ready: the proof is shown (a)', () => {
  it('reads the design through my-requests and renders the portal proof viewer with a pin target per tag', async () => {
    mount(LIMITED);
    expect(await screen.findByTestId('pin-hit-l-1')).toBeTruthy();
    expect(calls.some((c) => c.method === 'GET' && c.url.split('?')[0] === `${MINE}/req-1/design`)).toBe(true);
    expect(calls.some((c) => c.url.startsWith('/api/v1/dealer-kit/price-tag-requests') && /design/.test(c.url))).toBe(false);
  });

  it('reads the earlier change-request rounds through my-requests, like the portal does', async () => {
    mount(LIMITED);
    await screen.findByTestId('pin-hit-l-1');
    await waitFor(() =>
      expect(calls.some((c) => c.method === 'GET' && c.url.split('?')[0] === `${MINE}/req-1/review-comments`)).toBe(true),
    );
  });

  it('Approve sits with the proof and POSTs .../approve through my-requests', async () => {
    mount(LIMITED);
    await screen.findByTestId('pin-hit-l-1');
    const approve = (await screen.findAllByRole('button', { name: /^Approve/ }))[0];
    fireEvent.click(approve);
    await waitFor(() => expect(posted('approve')).toHaveLength(1));
  });

  it('a design that is not ready says so and offers no pin target', async () => {
    state.design = null;
    mount(LIMITED);
    expect(await screen.findByText('Design not available yet')).toBeTruthy();
    expect(screen.queryByTestId('pin-hit-l-1')).toBeNull();
  });

  it('after approval the proof stays visible but cannot take pins', async () => {
    mount(LIMITED, { status: 'approved' });
    await waitFor(() => expect(calls.some((c) => c.url.split('?')[0] === `${MINE}/req-1/design`)).toBe(true));
    expect(screen.queryByTestId('pin-hit-l-1')).toBeNull();
    expect(screen.queryByTestId('send-change-requests')).toBeNull();
  });
});

describe('limited user, request changes with pinned comments (b)', () => {
  it('no pin yet, no Send; the plain-note dialog is gone', async () => {
    mount(LIMITED);
    await screen.findByTestId('pin-hit-l-1');
    expect(screen.queryByTestId('send-change-requests')).toBeNull();
    expect(screen.queryByLabelText('Changes')).toBeNull();
  });

  it('two pins and a note go in ONE POST .../request-changes with the portal body shape', async () => {
    mount(LIMITED);
    await placePin('Make the price bigger');
    await placePin('Move the logo');
    fireEvent.change(await screen.findByLabelText(/Anything else \(optional\)/), { target: { value: 'Too busy overall' } });
    fireEvent.click(await screen.findByTestId('send-change-requests'));

    await waitFor(() => expect(posted('request-changes')).toHaveLength(1));
    const body = posted('request-changes')[0].body as { comments: Array<Record<string, unknown>>; note?: string };
    expect(body.comments).toHaveLength(2);
    expect(body.comments[0]).toMatchObject({ tag_id: 'l-1', w: 0, h: 0, body: 'Make the price bigger' });
    expect(body.comments[0].x as number).toBeCloseTo(0.25, 5);
    expect(body.comments[0].y as number).toBeCloseTo(0.5, 5);
    expect(body.comments[1]).toMatchObject({ tag_id: 'l-1', body: 'Move the logo' });
    expect(body.note).toBe('Too busy overall');
  });

  it('a note alone is also a valid round, as on the portal', async () => {
    mount(LIMITED);
    await screen.findByTestId('pin-hit-l-1');
    fireEvent.change(await screen.findByLabelText(/Anything else \(optional\)/), { target: { value: 'Redo it' } });
    fireEvent.click(await screen.findByTestId('send-change-requests'));
    await waitFor(() => expect(posted('request-changes')).toHaveLength(1));
    expect(posted('request-changes')[0].body).toMatchObject({ comments: [], note: 'Redo it' });
  });
});

describe('staff user (control, d)', () => {
  it('the staff page shows none of the salesperson review UI and calls nothing through my-requests', async () => {
    mount(STAFF);
    await screen.findByRole('heading', { level: 1, name: 'PT-202610-0001' });
    expect(screen.queryByTestId('send-change-requests')).toBeNull();
    expect(screen.queryByTestId('pin-hit-l-1')).toBeNull();
    expect(screen.queryByLabelText(/Anything else \(optional\)/)).toBeNull();
    expect(calls.filter((c) => c.url.startsWith('/api/v1/my-requests'))).toHaveLength(0);
  });
});
