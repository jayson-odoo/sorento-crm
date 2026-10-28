/**
 * PORTAL-P4-REQUESTS S7b round 2 (red): parity gaps between the CRM price tag request page (limited user)
 * and the portal form. Labels are the portal's own.
 *
 *  4. List price / Selling price radio on /new and ?edit=1; Selling offers the line Promotion; the save carries price_mode
 *  5. view mode Lines tab: List price column (Promotion + Selling price columns in selling mode) and each line's parts
 *  6. the proof viewer's Download PDF reads GET .../my-requests/submissions/price_tag_request/{id}/download
 *  staff control: none of it on the staff page
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
vi.mock('@/components/common/DetailActionsMenu', () => ({ DetailActionsMenu: () => null }));
vi.mock('@/components/common/AttachmentPreviewModal', () => ({ __esModule: true, default: () => null }));
vi.mock('@/lib/dealer-kit/fonts', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/dealer-kit/fonts')>();
  return { ...actual, ensureFontsLoaded: vi.fn(async () => {}), ensureSeedFontsLoaded: vi.fn(async () => {}) };
});

/** The portal suites' native-select stand-in: a pick is one change event. */
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    value: string;
    onChange: (v: string) => void;
    onOptionChange?: (o: { value: string; label: string } | null) => void;
    options?: { value: string; label: string }[];
    fetchOptions?: (q: string) => Promise<{ value: string; label: string }[]>;
    placeholder?: string;
  }) => {
    const [fetched, setFetched] = React.useState<{ value: string; label: string }[]>([]);
    React.useEffect(() => {
      if (props.fetchOptions) void props.fetchOptions('').then(setFetched);
    }, [props.fetchOptions]);
    const options = props.options ?? fetched;
    return (
      <select
        aria-label={props.placeholder ?? ''}
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

const calls: Array<{ url: string; method: string; body: unknown }> = [];
const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status, headers: { 'content-type': 'application/json' } });
const CABINET = { kind: 'product', id: 'prod-cabinet', code: 'SRTBF11834', name: 'ZZT Cabinet' };
const DESIGN = {
  page_id: 'page-1', version: 2, source: 'version',
  doc: {
    kind: 'tag_sheet', imposition: { page_width_mm: 210, page_height_mm: 297 },
    sheets: [{ id: 'sheet-1', tags: [{ id: 'tag-1', request_tag_id: 'l-1', x_mm: 20, y_mm: 30, width_mm: 80, height_mm: 40, layers: [] }] }],
  },
  lines: [], assets: {}, images: {}, fonts: [],
};
const apiFetch = vi.fn(async (url: string, init?: RequestInit) => {
  const method = (init?.method ?? 'GET').toUpperCase();
  let body: unknown = init?.body;
  if (typeof body === 'string') {
    try { body = JSON.parse(body); } catch { /* keep */ }
  }
  calls.push({ url, method, body });
  const path = url.split('?')[0];
  if (/\/api\/v1\/dealer-kit\/price-tag-requests\/req-1$/.test(path) && method === 'GET') return json(state.detail);
  if (/\/my-requests\/submissions\/price_tag_request\/req-1$/.test(path) && method === 'GET') return json(state.detail);
  if (path.endsWith('/req-1/design')) return json(DESIGN);
  if (path.endsWith('/req-1/download')) {
    return new Response('%PDF', { status: 200, headers: { 'content-type': 'application/pdf', 'content-disposition': 'attachment; filename="tags.pdf"' } });
  }
  if (path.endsWith('/lookups/price-tag-items')) return json([CABINET]);
  if (path.includes('/lookups/product-combos/')) return json({ host_guarded: false, combos: [] });
  if (path.endsWith('/lookups/line-pricing')) {
    const lines = (body as { lines: Array<{ key: string; candidate_product_ids?: string[] }> }).lines;
    return json(lines.map((l) => ({
      key: l.key, list_price: 100, sell_price: 90, sell_price_basis: 'promotion', auto_promotion_id: 'promo-1',
      promotion_options: [{ id: 'promo-1', description: 'ZZT Promo', sell_price: 90 }],
      parts_at_list: [],
      candidates: (l.candidate_product_ids ?? []).map((id) => ({ product_id: id, list_price: 10, sell_price: 10 })),
    })));
  }
  if (path.endsWith('/lookups/promotions')) return json([{ id: 'promo-1', description: 'ZZT Promo' }]);
  if (path.includes('/submissions/price_tag_request') && method !== 'GET') return json({ ...state.detail, id: 'req-1' });
  return json([]);
});
vi.mock('@/lib/api', () => ({ apiFetch: (...a: [string, RequestInit?]) => apiFetch(...a) }));

import PriceTagRequestPage from './PriceTagRequestPage';
import OwnPriceTagRequest from './OwnPriceTagRequest';

const LIMITED = ['dealer_kit.price_tag_requests.view_own', 'dealer_kit.price_tag_requests.create'];
const STAFF = ['dealer_kit.price_tag_requests.view', 'dealer_kit.price_tag_requests.process'];
const MINE = '/api/v1/my-requests/submissions/price_tag_request';
const MIRROR = { product_id: 'prod-mirror', code: 'SRTMR502-BL', name: 'ZZT Mirror' };

function detail(over: Record<string, unknown> = {}) {
  return {
    id: 'req-1', contact_id: 'ct-1', doc_number: 'PT-202610-0001', status: 'new', portal_draft_at: '2026-10-01T01:00:00',
    debtor_code: 'D-001', debtor_name: 'ZZT Dealer', needed_by_date: null, notes: null, price_mode: 'list',
    print_by: 'self', created_at: '2026-10-01T01:00:00', assigned_to_id: null, assigned_to_name: null,
    contact_name: 'Sales Sam', line_count: 1, data_changed_tag_count: 0, revision_no: 0, attachments: [], review_round: 0,
    revision: { enabled: true, allowed: false, used: 0, max: 3, remaining: 3, blocked_reason: null },
    lines: [{
      id: 'l-1', line_type: 'product', product_id: CABINET.id, product_set_id: null, name: CABINET.name, code: CABINET.code,
      show_promo_price: false, quantity: 2, included_accessories: null, remarks: null, sort_order: 0,
      list_price: 100, sell_price: 90, promotion_id: 'promo-1', promotion_name: 'ZZT Promo', combo_id: null,
      parts: [{ id: 'pt-1', product_id: MIRROR.product_id, code: MIRROR.code, name: MIRROR.name, role: null, candidates: [] }],
      package_warning: null, tags: [{ id: 'l-1', label: '1a', quantity: 2, open_groups: [], choices_display: [] }],
    }],
    ...over,
  };
}

const client = () => new QueryClient({ defaultOptions: { queries: { retry: false } } });
function mountPage(slugs: string[], over: Record<string, unknown> = {}, search = '') {
  state.perms = new Set(slugs);
  state.search = search;
  state.detail = detail(over);
  return render(<QueryClientProvider client={client()}><PriceTagRequestPage requestId="req-1" /></QueryClientProvider>);
}
function mountNew() {
  state.perms = new Set(LIMITED);
  state.search = '';
  state.detail = detail({ id: 'new-1', portal_draft_at: null, lines: [] });
  return render(<QueryClientProvider client={client()}><OwnPriceTagRequest /></QueryClientProvider>);
}
async function clickTab(name: RegExp) {
  const tab = await screen.findByRole('tab', { name });
  fireEvent.mouseDown(tab);
  fireEvent.click(tab);
}
async function pick(label: string | RegExp, value: string) {
  await screen.findByLabelText(label);
  await waitFor(() =>
    expect(Array.from((screen.getByLabelText(label) as HTMLSelectElement).options).map((o) => o.value)).toContain(value),
  );
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
}
const saved = (method: 'POST' | 'PUT') =>
  calls.filter((c) => c.method === method && c.url.split('?')[0].startsWith(MINE) && !/\/(submit|approve|collect)$/.test(c.url));

beforeEach(() => {
  calls.length = 0;
  (URL as unknown as Record<string, unknown>).createObjectURL = vi.fn(() => 'blob:x');
  (URL as unknown as Record<string, unknown>).revokeObjectURL = vi.fn();
});
afterEach(cleanup);

describe('4. List price / Selling price control', () => {
  it('/new offers the portal radio, List selected by default', async () => {
    mountNew();
    const list = await screen.findByRole('radio', { name: 'List price' });
    expect(screen.getByRole('radio', { name: 'Selling price' })).toBeTruthy();
    expect(list.getAttribute('aria-checked')).not.toBe('false');
  });

  it('/new: choosing Selling offers the line Promotion and Save as draft posts price_mode and promotion_id', async () => {
    mountNew();
    fireEvent.click(await screen.findByRole('radio', { name: 'Selling price' }));
    await clickTab(/Lines/);
    await pick(/product or set|set or product/i, `product:${CABINET.id}`);
    await pick(/No covering promotion|Promotion/, 'promo-1');
    fireEvent.click(screen.getByRole('button', { name: /Save as draft/ }));
    await waitFor(() => expect(saved('POST')).toHaveLength(1));
    const body = saved('POST')[0].body as { price_mode?: string; lines: Array<Record<string, unknown>> };
    expect(body.price_mode).toBe('selling');
    expect(body.lines[0]).toMatchObject({ promotion_id: 'promo-1' });
  });

  it('?edit=1 on a list draft: switching to Selling saves price_mode selling', async () => {
    mountPage(LIMITED, {}, 'edit=1');
    fireEvent.click(await screen.findByRole('radio', { name: 'Selling price' }));
    fireEvent.click(screen.getByRole('button', { name: /Save as draft/ }));
    await waitFor(() => expect(saved('PUT')).toHaveLength(1));
    expect((saved('PUT')[0].body as { price_mode?: string }).price_mode).toBe('selling');
  });

  it('staff control: no price mode radio on the staff page', async () => {
    mountPage(STAFF, { portal_draft_at: null });
    await screen.findByRole('heading', { level: 1, name: 'PT-202610-0001' });
    expect(screen.queryByRole('radio', { name: 'Selling price' })).toBeNull();
  });
});

describe('5. view-mode Lines tab shows the portal price columns and parts', () => {
  it('list mode: a List price column and the line parts, no Promotion or Selling columns', async () => {
    mountPage(LIMITED, { price_mode: 'list' });
    await clickTab(/Lines/);
    expect(await screen.findByRole('columnheader', { name: 'List price' })).toBeTruthy();
    expect(screen.queryByRole('columnheader', { name: 'Promotion' })).toBeNull();
    expect(screen.queryByRole('columnheader', { name: 'Selling price' })).toBeNull();
    expect(screen.getByText(MIRROR.code)).toBeTruthy();
  });

  it('selling mode: List price, Promotion and Selling price columns with the line promotion name', async () => {
    mountPage(LIMITED, { price_mode: 'selling' });
    await clickTab(/Lines/);
    for (const name of ['List price', 'Promotion', 'Selling price']) {
      expect(await screen.findByRole('columnheader', { name }), name).toBeTruthy();
    }
    expect(screen.getByText(/ZZT Promo/)).toBeTruthy();
  });
});

describe('6. proof viewer Download', () => {
  it('Download PDF in the viewer GETs .../{id}/download through my-requests', async () => {
    mountPage(LIMITED, { status: 'approved', portal_draft_at: null, latest_export_status: 'ready', has_completed_export: true });
    fireEvent.click(await screen.findByRole('button', { name: /^Open/ }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.click(await within(dialog).findByRole('button', { name: /Download PDF/ }));
    await waitFor(() => expect(calls.some((c) => c.method === 'GET' && c.url.split('?')[0] === `${MINE}/req-1/download`)).toBe(true));
    expect(calls.some((c) => c.url.includes('/public/portal'))).toBe(false);
  });

  it('staff control: the staff page makes no my-requests download call', async () => {
    mountPage(STAFF, { status: 'approved', portal_draft_at: null });
    await screen.findByRole('heading', { level: 1, name: 'PT-202610-0001' });
    expect(calls.filter((c) => c.url.startsWith('/api/v1/my-requests'))).toHaveLength(0);
  });
});
