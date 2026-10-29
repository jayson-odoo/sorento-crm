/**
 * PORTAL-P4-REQUESTS R3a (form parity, PAR-1/3/5): a LIMITED user (`view_own`, not `view`) logs, views and edits a
 * Sales Opportunity through the PORTAL's own components (app/(auth)/portal/sales_opportunity/components), wired to
 * `/api/v1/my-requests` by an injected client. Entry points are the components the pages render:
 * SalesOpportunityModal (Log opportunity, opened from the list) and SalesOpportunityDetail (view + in-place edit +
 * stage moves). Staff keep today's modal and detail.
 *
 * Markers that tell the PORTAL from the CRM: the my-requests vs staff call checks (the staff modal has the same "Customer or prospect" label, so the label is no marker); the detail's gear is the portal's own `DetailActionsMenu` labelled "Actions" (the CRM detail uses
 * `DetailActions`, mocked here with data-testid="detail-actions").
 *
 * The SearchableSelect is a native <select> here (same stand-in the portal and CRM opportunity tests use).
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const nav = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn() }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: nav.push, replace: nav.replace, back: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => '/sales/opportunities',
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } }));
vi.mock('@/components/common/RecordNavigation', () => ({ RecordNavigation: () => <nav aria-label="record navigation" /> }));
vi.mock('@/hooks/useDeferredAction', () => ({ useDeferredAction: () => ({ countdown: null, isBlocked: false, isPending: false, start: vi.fn() }) }));
vi.mock('@/components/common/DetailActions', () => ({
  default: ({ pagerNode, actions, primary, pendingAction }: {
    pagerNode?: React.ReactNode;
    actions?: { key: string; label: string; run: () => void; disabled?: boolean }[];
    primary?: React.ReactNode;
    pendingAction?: React.ReactNode;
  }) => (
    <div data-testid="detail-actions">
      {pagerNode}
      <div data-testid="gear">
        {(actions ?? []).map((a) => (
          <button key={a.key} type="button" disabled={a.disabled} onClick={() => a.run()}>{a.label}</button>
        ))}
      </div>
      {pendingAction ?? primary}
    </div>
  ),
}));
vi.mock('@/components/common/DetailActionsMenu', () => ({
  DetailActionsMenu: ({ actions, ariaLabel }: { actions?: { key: string; label: string; run: () => void }[]; ariaLabel?: string }) => (
    <div aria-label={ariaLabel} data-testid="portal-gear">
      {(actions ?? []).map((a) => (
        <button key={a.key} type="button" onClick={() => a.run()}>{a.label}</button>
      ))}
    </div>
  ),
}));
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    id?: string;
    'aria-label'?: string;
    value: string;
    onChange: (v: string) => void;
    onOptionChange?: (o: { value: string; label: string; disabled?: boolean } | null) => void;
    options?: { value: string; label: string; disabled?: boolean }[];
    fetchOptions?: (q: string, page: number) => Promise<{ value: string; label: string; disabled?: boolean }[]>;
    selectedOption?: { value: string; label: string; disabled?: boolean };
    placeholder?: string;
  }) => {
    const [query, setQuery] = React.useState('');
    const [options, setOptions] = React.useState(props.options ?? []);
    React.useEffect(() => {
      if (props.fetchOptions) void props.fetchOptions(query, 0).then(setOptions);
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [query]);
    const label = props['aria-label'] ?? props.placeholder ?? props.id ?? 'select';
    const merged =
      props.selectedOption && !options.some((o) => o.value === props.selectedOption!.value)
        ? [props.selectedOption, ...options]
        : options;
    return (
      <div>
        {props.fetchOptions ? <input aria-label={`${label} search`} value={query} onChange={(e) => setQuery(e.target.value)} /> : null}
        <select
          aria-label={label}
          value={props.value}
          onChange={(e) => {
            props.onChange(e.target.value);
            props.onOptionChange?.(merged.find((o) => o.value === e.target.value) ?? null);
          }}
        >
          <option value="" />
          {merged.map((o) => (
            <option key={o.value} value={o.value} disabled={o.disabled}>{o.label}</option>
          ))}
        </select>
      </div>
    );
  },
}));

let held = new Set<string>();
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => held.has(slug),
  useHasAnyPermission: (slugs: string[]) => slugs.some((s) => held.has(s)),
  usePermissions: () => ({ permissionSet: held, permissions: [...held], isLoading: false, isError: false }),
}));

interface Call { url: string; method: string; body: unknown }
const calls: Call[] = [];
const MINE = '/api/v1/my-requests/sales-opportunities';
const STAFF_BASE = '/api/v1/sales/opportunities';
const opp = {
  id: 'opp-1', opportunity_no: 'OPP-000001', title: 'ZZT Deal', customer_id: 'cust-1', customer_name: 'ZZT Dealer',
  prospect_name: null, sales_agent_id: 'ag-1', sales_agent_label: 'ZZA-1', status_id: 'st-new', stage_key: 'new',
  stage_label: 'New', win_probability: 10, outcome: 'open', expected_amount: '1000.00', expected_close_date: '2026-11-01',
  lost_reason: null, lost_reason_label: null, sales_order_id: null, sales_order_no: null, source: 'portal',
  created_by_label: 'Ann Sales', created_at: '2026-09-26T00:00:00', updated_at: '2026-09-26T00:00:00',
  stage_changed_at: '2026-09-26T00:00:00', lines: [],
  available_transitions: [
    { to_status_id: 'st-qualified', key: 'qualified', label: 'Qualified' },
    { to_status_id: 'st-won', key: 'won', label: 'Won' },
    { to_status_id: 'st-lost', key: 'lost', label: 'Lost' },
  ],
};
let patchRefusal: { message: string } | null = null;
const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status, headers: { 'content-type': 'application/json' } });
vi.mock('@/lib/api', () => ({
  apiFetch: async (url: string, init?: RequestInit) => {
    const method = (init?.method ?? 'GET').toUpperCase();
    let body: unknown = init?.body;
    if (typeof body === 'string') {
      try { body = JSON.parse(body); } catch { /* keep */ }
    }
    calls.push({ url, method, body });
    const path = url.split('?')[0];
    if (path.endsWith('/meta')) return json({ stages: [], lost_reasons: [{ value: 'price', label: 'Price' }] });
    if (path.includes('agent-options') || path.includes('sales-order-options')) return json({ data: [] });
    if (path.endsWith('/customer-options'))
      return json({ items: [{ customer_id: 'cust-1', customer_code: 'C1', customer_name: 'ZZT Mine', label: 'C1 - ZZT Mine' }], prospect: null, blocked: null });
    if (path === '/api/v1/my-requests/lookups/products')
      return json([{ product_id: 'p1', product_code: 'ZZT-001', product_name: 'ZZT Basin', list_price: '100.00' }]);
    if (method === 'POST') return json({ ...opp, id: 'opp-new' });
    if (method === 'PATCH') return patchRefusal ? json(patchRefusal, 422) : json(opp);
    if (path.endsWith('/opp-1')) return json(opp);
    return json({ data: [opp], pagination: { total: 1, page: 1, limit: 200 }, empty: false });
  },
}));

import SalesOpportunityModal from './SalesOpportunityModal';
import SalesOpportunityDetail from '../[id]/components/SalesOpportunityDetail';
import { toast } from '@/lib/toast';

const LIMITED = ['sales.opportunities.view_own', 'sales.opportunities.add', 'sales.opportunities.edit'];
const STAFF = ['sales.opportunities.view', 'sales.opportunities.add', 'sales.opportunities.edit', 'sales.opportunities.delete'];
const where = (pred: (c: Call) => boolean) => calls.filter(pred);
const portalCalls = () => where((c) => c.url.startsWith('/api/v1/public/portal'));
const staffApi = () => where((c) => c.url.startsWith(STAFF_BASE));

function wrap(node: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
}
function mountModal(slugs: string[]) {
  held = new Set(slugs);
  return wrap(<SalesOpportunityModal open onOpenChange={onOpenChange} />);
}
const onOpenChange = vi.fn();
function mountDetail(slugs: string[]) {
  held = new Set(slugs);
  return wrap(<SalesOpportunityDetail id="opp-1" />);
}

beforeEach(() => {
  cleanup();
  calls.length = 0;
  vi.clearAllMocks();
  patchRefusal = null;
});

describe('limited user, Log opportunity renders the portal create form', () => {
  it('the dialog body is the portal form ("Log a sales opportunity"), searching my-requests only', async () => {
    mountModal(LIMITED);
    const dialog = await screen.findByRole('dialog');
    expect(await within(dialog).findByLabelText('Customer or prospect')).toBeInTheDocument();
    await waitFor(() => expect(where((c) => c.url.startsWith(`${MINE}/customer-options`)).length).toBeGreaterThan(0));
    expect(staffApi()).toHaveLength(0);
    expect(portalCalls()).toHaveLength(0);
  });

  it('the dialog names the action once: the DialogTitle stays, the portal card title is not rendered', async () => {
    mountModal(LIMITED);
    const dialog = await screen.findByRole('dialog');
    await within(dialog).findByLabelText('Customer or prospect');
    expect(within(dialog).getByRole('heading', { name: 'Log opportunity' })).toBeInTheDocument();
    expect(within(dialog).queryByText('Log a sales opportunity')).toBeNull();
    expect(within(dialog).queryByText(/^Log (a sales )?opportunity$/i, { selector: '[data-slot="card-title"]' })).toBeNull();
  });

  it('Save POSTs exactly the portal body to my-requests, then pushes the CRM detail (never /portal)', async () => {
    mountModal(LIMITED);
    const dialog = await screen.findByRole('dialog');
    await within(dialog).findByLabelText('Customer or prospect');
    const customer = screen.getByLabelText('Customer or prospect');
    await waitFor(() => expect((customer as HTMLSelectElement).options.length).toBeGreaterThan(1));
    fireEvent.change(customer, { target: { value: 'cust-1' } });
    fireEvent.change(screen.getByLabelText('Title'), { target: { value: 'ZZT Deal' } });
    fireEvent.change(screen.getByLabelText('Expected close date'), { target: { value: '2026-12-01' } });
    fireEvent.click(screen.getByRole('button', { name: /Add product/ }));
    const product = await screen.findByLabelText('Search products...');
    await waitFor(() => expect((product as HTMLSelectElement).options.length).toBeGreaterThan(1));
    fireEvent.change(product, { target: { value: 'p1' } });
    expect(where((c) => c.url.startsWith('/api/v1/my-requests/lookups/products')).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole('button', { name: /^Save$/ }));
    await waitFor(() => expect(where((c) => c.method === 'POST' && c.url === MINE)).toHaveLength(1));
    expect(where((c) => c.method === 'POST' && c.url === MINE)[0].body).toEqual({
      title: 'ZZT Deal',
      expected_amount: '100.00',
      expected_close_date: '2026-12-01',
      customer_id: 'cust-1',
      lines: [{ product_id: 'p1', qty: 1, unit_price: 100 }],
    });
    await waitFor(() => expect(nav.push).toHaveBeenCalledWith('/sales/opportunities/opp-new'));
    expect(nav.push.mock.calls.every((a) => !String(a[0]).startsWith('/portal'))).toBe(true);
    expect(staffApi().filter((c) => c.method !== 'GET')).toHaveLength(0);
  });
});

describe('limited user, Sales Opportunity detail renders the portal detail', () => {
  it('reads my-requests (record + meta), has the portal gear, and never the staff API or DetailActions', async () => {
    mountDetail(LIMITED);
    expect(await screen.findByLabelText('Actions')).toBeInTheDocument();
    expect(screen.queryByTestId('detail-actions')).toBeNull();
    await waitFor(() => expect(where((c) => c.method === 'GET' && c.url === `${MINE}/opp-1`).length).toBeGreaterThan(0));
    expect(where((c) => c.url === `${MINE}/meta`).length).toBeGreaterThan(0);
    expect(staffApi()).toHaveLength(0);
    expect(portalCalls()).toHaveLength(0);
  });

  it('in-place edit PATCHes my-requests/<id> with the new title', async () => {
    mountDetail(LIMITED);
    fireEvent.click(await screen.findByRole('button', { name: /^edit$/i }));
    fireEvent.change(await screen.findByDisplayValue('ZZT Deal'), { target: { value: 'ZZT Renamed' } });
    fireEvent.click(screen.getByRole('button', { name: /^save/i }));
    await waitFor(() => expect(where((c) => c.method === 'PATCH' && c.url === `${MINE}/opp-1`)).toHaveLength(1));
    expect(where((c) => c.method === 'PATCH')[0].body).toMatchObject({ title: 'ZZT Renamed' });
    expect(where((c) => c.method === 'PATCH' && c.url.startsWith(STAFF_BASE))).toHaveLength(0);
  });

  it('a stage move (Qualified) PATCHes my-requests with status_id', async () => {
    mountDetail(LIMITED);
    fireEvent.click(await within(await screen.findByTestId('portal-gear')).findByRole('button', { name: 'Qualified' }));
    await waitFor(() => expect(where((c) => c.method === 'PATCH' && c.url === `${MINE}/opp-1`)).toHaveLength(1));
    expect(where((c) => c.method === 'PATCH')[0].body).toMatchObject({ status_id: 'st-qualified' });
  });

  it('shows no delete, and any back link points at the CRM list, never /portal', async () => {
    mountDetail(LIMITED);
    await screen.findByLabelText('Actions');
    expect(screen.queryByRole('button', { name: /delete/i })).toBeNull();
    for (const link of screen.queryAllByRole('link')) {
      expect(link.getAttribute('href') ?? '').not.toContain('/portal');
    }
    expect(screen.queryByRole('button', { name: /^Back/ })).toBeNull();
    expect(screen.queryByRole('link', { name: /Back/ })).toBeNull();
  });

  it('a refused PATCH shows the server message in a toast', async () => {
    patchRefusal = { message: 'ZZT refusal text' };
    mountDetail(LIMITED);
    fireEvent.click(await screen.findByRole('button', { name: /^edit$/i }));
    fireEvent.change(await screen.findByDisplayValue('ZZT Deal'), { target: { value: 'ZZT Renamed' } });
    fireEvent.click(screen.getByRole('button', { name: /^save/i }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('ZZT refusal text'));
    expect(where((c) => c.method === 'PATCH' && c.url === `${MINE}/opp-1`)).toHaveLength(1);
  });
});

describe('staff keep today\'s Sales Opportunity screens', () => {
  it('staff Log opportunity is the staff modal: no portal title, staff create route, nothing on my-requests', async () => {
    mountModal(STAFF);
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).queryByText('Log a sales opportunity')).toBeNull();
    const customer = screen.getByLabelText('Customer or prospect');
    await waitFor(() => expect((customer as HTMLSelectElement).options.length).toBeGreaterThan(1));
    fireEvent.change(customer, { target: { value: 'cust-1' } });
    fireEvent.change(screen.getByLabelText('Title'), { target: { value: 'ZZT Deal' } });
    fireEvent.change(screen.getByLabelText('Expected close date'), { target: { value: '2026-12-01' } });
    fireEvent.click(screen.getByRole('button', { name: /^Save$/ }));
    await waitFor(() => expect(where((c) => c.method === 'POST' && c.url === STAFF_BASE)).toHaveLength(1));
    expect(where((c) => c.url.startsWith('/api/v1/my-requests'))).toHaveLength(0);
  });

  it('staff detail keeps DetailActions and the staff PATCH', async () => {
    mountDetail(STAFF);
    const gear = within(await screen.findByTestId('gear'));
    expect(screen.queryByTestId('portal-gear')).toBeNull();
    fireEvent.click(await gear.findByRole('button', { name: 'Qualified' }));
    await waitFor(() => expect(where((c) => c.method === 'PATCH' && c.url === `${STAFF_BASE}/opp-1`)).toHaveLength(1));
    expect(where((c) => c.url.startsWith('/api/v1/my-requests'))).toHaveLength(0);
  });
});
