/**
 * PORTAL-P4-REQUESTS S7b (red): the portal's per-line combo / part / promotion controls inside the CRM price
 * tag request page's edit and new modes, for a LIMITED user. The CRM reuses the portal's line editor (today
 * inline in PriceTagRequestForm.tsx) rather than its own qty / add / remove rows. Asserted at the HTTP seam:
 *
 *  - lookups go to /api/v1/my-requests/lookups/{price-tag-items, product-combos/{pid}, line-pricing}
 *  - saving sends the SAME line payload the portal sends (PriceTagRequestLineInput: combo_id, parts[], ...)
 *  - the portal's labels are kept: `Package`, `Not sure, any of N`, `Promotion`
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const state = vi.hoisted(() => ({
  perms: new Set<string>(),
  search: '',
  detail: {} as Record<string, unknown>,
  combos: { host_guarded: true, combos: [] as unknown[] } as Record<string, unknown>,
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

/** The same native-select stand-in the portal's own form suites use: a pick is one change event. */
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
const apiFetch = vi.fn(async (url: string, init?: RequestInit) => {
  const method = (init?.method ?? 'GET').toUpperCase();
  let body: unknown = init?.body;
  if (typeof body === 'string') {
    try { body = JSON.parse(body); } catch { /* keep */ }
  }
  calls.push({ url, method, body });
  const path = url.split('?')[0];
  if (/\/api\/v1\/dealer-kit\/price-tag-requests\/req-1$/.test(path) && method === 'GET') return json(state.detail);
  if (path.endsWith('/lookups/price-tag-items')) return json([CABINET]);
  if (path.includes('/lookups/product-combos/')) return json(state.combos);
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
  if (path.includes('/lookups/debtors-for-agent')) return json([]);
  if (/\/my-requests\/submissions\/price_tag_request\/req-1$/.test(path) && method === 'GET') return json(state.detail);
  if (path.includes('/submissions/price_tag_request') && method !== 'GET') return json({ ...state.detail, id: 'req-1' });
  return json([]);
});
vi.mock('@/lib/api', () => ({ apiFetch: (...a: [string, RequestInit?]) => apiFetch(...a) }));

import PriceTagRequestPage from './PriceTagRequestPage';
import OwnPriceTagRequest from './OwnPriceTagRequest';

const LIMITED = ['dealer_kit.price_tag_requests.view_own', 'dealer_kit.price_tag_requests.create'];
const STAFF = ['dealer_kit.price_tag_requests.view', 'dealer_kit.price_tag_requests.process'];
const MINE = '/api/v1/my-requests/submissions/price_tag_request';
const LOOKUPS = '/api/v1/my-requests/lookups';

const MIRROR = { product_id: 'prod-mirror', code: 'SRTMR502-BL', name: 'ZZT Mirror' };
const BASIN_WHITE = { product_id: 'prod-basin-wh', code: 'SRTBS900-WH', name: 'ZZT Basin White' };
const BASIN_BLACK = { product_id: 'prod-basin-bk', code: 'SRTBS900-BK', name: 'ZZT Basin Black' };
const COMBO_3_IN_1 = {
  combo_id: 'combo-3',
  name: '3 in 1',
  parts: [
    { ...MIRROR, choice_group: null },
    { ...BASIN_WHITE, choice_group: 'Basin' },
    { ...BASIN_BLACK, choice_group: 'Basin' },
  ],
};
const COMBO_4_IN_1 = { combo_id: 'combo-4', name: '4 in 1', parts: [{ ...MIRROR, choice_group: null }] };

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
      list_price: 100, sell_price: 100, parts: [], package_warning: null, combo_id: null, tags: [],
    }],
    ...over,
  };
}

function client() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}
function mountEdit(slugs: string[], over: Record<string, unknown> = {}) {
  state.perms = new Set(slugs);
  state.search = 'edit=1';
  state.detail = detail(over);
  return render(<QueryClientProvider client={client()}><PriceTagRequestPage requestId="req-1" /></QueryClientProvider>);
}
function mountNew() {
  state.perms = new Set(LIMITED);
  state.search = '';
  state.detail = detail({ id: 'new-1', portal_draft_at: null, lines: [] });
  return render(<QueryClientProvider client={client()}><OwnPriceTagRequest /></QueryClientProvider>);
}

const ITEM_PICKER = /product or set|set or product/i;
const saved = (method: 'POST' | 'PUT') =>
  calls.filter((c) => c.method === method && c.url.split('?')[0].startsWith(MINE) && !/\/(submit|approve|collect)$/.test(c.url));
type SavedLine = Record<string, unknown> & { parts?: unknown[] };
const savedLines = (method: 'POST' | 'PUT') => (saved(method)[0].body as { lines: SavedLine[] }).lines;

/** Pick an option by firing one change event. The CRM add-line picker resets itself after a pick, so unlike the
 *  shared `selectOption` this does not assert the select keeps the value. */
async function selectOption(label: string | RegExp, value: string) {
  await screen.findByLabelText(label);
  await waitFor(() =>
    expect(Array.from((screen.getByLabelText(label) as HTMLSelectElement).options).map((o) => o.value)).toContain(value),
  );
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
}

async function clickTab(name: RegExp) {
  const tab = await screen.findByRole('tab', { name });
  fireEvent.mouseDown(tab);
  fireEvent.click(tab);
}

beforeEach(() => {
  calls.length = 0;
  state.combos = { host_guarded: true, combos: [COMBO_3_IN_1] };
});
afterEach(cleanup);

describe('/new: a picked product brings its package and parts (c)', () => {
  it('asks my-requests for the packages of the picked product, once', async () => {
    mountNew();
    await clickTab(/Lines/);
    const add = screen.queryByRole('button', { name: /Add line/ });
    if (add) fireEvent.click(add);
    await selectOption(ITEM_PICKER, `product:${CABINET.id}`);
    await waitFor(() => expect(calls.some((c) => c.url === `${LOOKUPS}/product-combos/${CABINET.id}`)).toBe(true));
    expect(calls.filter((c) => c.url.startsWith(`${LOOKUPS}/product-combos/`))).toHaveLength(1);
    expect(calls.filter((c) => c.url.includes('/public/portal'))).toHaveLength(0);
  });

  it('the only package fills in: fixed part by code, one open row per choice group; prices come from my-requests line-pricing', async () => {
    mountNew();
    await clickTab(/Lines/);
    const add = screen.queryByRole('button', { name: /Add line/ });
    if (add) fireEvent.click(add);
    await selectOption(ITEM_PICKER, `product:${CABINET.id}`);
    expect(await screen.findByText(MIRROR.code)).toBeTruthy();
    expect(screen.getByLabelText('Not sure, any of 2')).toBeTruthy();
    await waitFor(() => expect(screen.queryByText(BASIN_WHITE.code)).toBeNull());
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.url === `${LOOKUPS}/line-pricing`)).toBe(true));
    const body = calls.find((c) => c.url === `${LOOKUPS}/line-pricing`)!.body as { lines: unknown[] };
    expect(Array.isArray(body.lines)).toBe(true);
  });

  it('Save as draft posts the portal line payload: combo_id and parts (fixed and open), no alternatives', async () => {
    mountNew();
    await clickTab(/Lines/);
    const add = screen.queryByRole('button', { name: /Add line/ });
    if (add) fireEvent.click(add);
    await selectOption(ITEM_PICKER, `product:${CABINET.id}`);
    await screen.findByText(MIRROR.code);
    fireEvent.click(screen.getByRole('button', { name: /Save as draft/ }));
    await waitFor(() => expect(saved('POST')).toHaveLength(1));
    const [line] = savedLines('POST');
    expect(line).toMatchObject({ line_type: 'product', product_id: CABINET.id, combo_id: COMBO_3_IN_1.combo_id });
    expect(line.parts).toEqual([
      { product_id: MIRROR.product_id, role: null, candidates: [] },
      { product_id: null, role: 'Basin', candidates: [BASIN_WHITE.product_id, BASIN_BLACK.product_id] },
    ]);
    expect(line.alternatives).toBeUndefined();
  });

  it('with two packages, Package is offered and nothing fills until one is chosen', async () => {
    state.combos = { host_guarded: true, combos: [COMBO_3_IN_1, COMBO_4_IN_1] };
    mountNew();
    await clickTab(/Lines/);
    const add = screen.queryByRole('button', { name: /Add line/ });
    if (add) fireEvent.click(add);
    await selectOption(ITEM_PICKER, `product:${CABINET.id}`);
    const pkg = await screen.findByLabelText('Package');
    expect(pkg.textContent).toContain('3 in 1');
    expect(pkg.textContent).toContain('4 in 1');
    expect(screen.queryByText(MIRROR.code)).toBeNull();
  });
});

describe('?edit=1 on a draft: existing lines get the same controls (c)', () => {
  it('reads the packages for the line already on the draft', async () => {
    mountEdit(LIMITED);
    await clickTab(/Lines/);
    await waitFor(() => expect(calls.some((c) => c.url === `${LOOKUPS}/product-combos/${CABINET.id}`)).toBe(true));
  });

  it('choosing a package then Save as draft PUTs the portal line payload', async () => {
    state.combos = { host_guarded: true, combos: [COMBO_3_IN_1, COMBO_4_IN_1] };
    mountEdit(LIMITED);
    await clickTab(/Lines/);
    await selectOption('Package', COMBO_3_IN_1.combo_id);
    await screen.findByText(MIRROR.code);
    fireEvent.click(screen.getByRole('button', { name: /Save as draft/ }));
    await waitFor(() => expect(saved('PUT')).toHaveLength(1));
    const [line] = savedLines('PUT');
    expect(line).toMatchObject({ product_id: CABINET.id, quantity: 2, combo_id: COMBO_3_IN_1.combo_id });
    expect(line.parts).toEqual([
      { product_id: MIRROR.product_id, role: null, candidates: [] },
      { product_id: null, role: 'Basin', candidates: [BASIN_WHITE.product_id, BASIN_BLACK.product_id] },
    ]);
  });

  it('a selling-price draft offers the line Promotion and PUTs the chosen promotion_id', async () => {
    state.combos = { host_guarded: false, combos: [] };
    mountEdit(LIMITED, { price_mode: 'selling' });
    await clickTab(/Lines/);
    await selectOption(/No covering promotion|Promotion/, 'promo-1');
    fireEvent.click(screen.getByRole('button', { name: /Save as draft/ }));
    await waitFor(() => expect(saved('PUT')).toHaveLength(1));
    expect(savedLines('PUT')[0]).toMatchObject({ promotion_id: 'promo-1' });
  });

  it('every lookup stays on my-requests', async () => {
    mountEdit(LIMITED);
    await clickTab(/Lines/);
    await waitFor(() => expect(calls.some((c) => c.url.includes('/lookups/'))).toBe(true));
    expect(calls.filter((c) => c.url.includes('/lookups/') && !c.url.startsWith('/api/v1/my-requests/'))).toHaveLength(0);
  });
});

describe('staff user (control, d)', () => {
  it('the staff request page offers no Package, open part row or my-requests lookup', async () => {
    state.perms = new Set(STAFF);
    state.search = '';
    state.detail = detail({ status: 'new', portal_draft_at: null });
    render(<QueryClientProvider client={client()}><PriceTagRequestPage requestId="req-1" /></QueryClientProvider>);
    await screen.findByRole('heading', { level: 1, name: 'PT-202610-0001' });
    expect(screen.queryByLabelText('Package')).toBeNull();
    expect(screen.queryByLabelText(/Not sure, any of/)).toBeNull();
    expect(calls.filter((c) => c.url.startsWith('/api/v1/my-requests'))).toHaveLength(0);
  });
});
