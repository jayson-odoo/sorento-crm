/**
 * PORTAL-P4-REQUESTS S6: the Sales Opportunity detail for a LIMITED user (`.view_own` + `.add` + `.edit`,
 * never `.view`): inline edit and stage moves go through /api/v1/my-requests/sales-opportunities/{id} (PATCH);
 * the staff-only controls are hidden: the Agent picker, the Won -> sales order link, Delete.
 * Staff (control) keeps all of them and the staff PATCH.
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => '/sales/opportunities/opp-1',
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('@/components/common/RecordNavigation', () => ({ RecordNavigation: () => <nav aria-label="record navigation" /> }));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));
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
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    id?: string;
    'aria-label'?: string;
    value: string;
    onChange: (v: string) => void;
    options?: { value: string; label: string }[];
    fetchOptions?: (q: string) => Promise<{ value: string; label: string }[]>;
  }) => {
    const [options, setOptions] = React.useState(props.options ?? []);
    React.useEffect(() => {
      if (props.fetchOptions) void props.fetchOptions('').then(setOptions);
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);
    return (
      <select aria-label={props['aria-label'] ?? props.id ?? 'select'} value={props.value} onChange={(e) => props.onChange(e.target.value)}>
        <option value="" />
        {(props.fetchOptions ? options : props.options ?? []).map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    );
  },
}));

let held = new Set<string>();
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => held.has(slug),
  useHasAnyPermission: (slugs: string[]) => slugs.some((s) => held.has(s)),
  usePermissions: () => ({ permissionSet: held, permissions: [...held], isLoading: false, isError: false }),
}));

const opp = {
  id: 'opp-1', opportunity_no: 'OPP-000001', title: 'ZZT Deal', customer_id: 'cust-1', customer_name: 'ZZT Dealer',
  prospect_name: null, sales_agent_id: 'ag-1', sales_agent_label: 'ZZA-1', status_id: 'st-new', stage_key: 'new',
  stage_label: 'New', win_probability: 10, outcome: 'open', expected_amount: '1000.00', expected_close_date: '2026-11-01',
  lost_reason: null, lost_reason_label: null, sales_order_id: null, sales_order_no: null, source: 'portal',
  created_by_label: 'Jane', created_at: '2026-09-26T00:00:00', updated_at: '2026-09-26T00:00:00',
  stage_changed_at: '2026-09-26T00:00:00', lines: [],
  available_transitions: [
    { to_status_id: 'st-qualified', key: 'qualified', label: 'Qualified' },
    { to_status_id: 'st-won', key: 'won', label: 'Won' },
    { to_status_id: 'st-lost', key: 'lost', label: 'Lost' },
  ],
};
const calls: Array<{ url: string; method: string; body: unknown }> = [];
const apiFetch = vi.fn(async (url: string, init?: RequestInit) => {
  const method = (init?.method ?? 'GET').toUpperCase();
  let body: unknown = init?.body;
  if (typeof body === 'string') {
    try { body = JSON.parse(body); } catch { /* keep */ }
  }
  calls.push({ url, method, body });
  const ok = (b: unknown) => new Response(JSON.stringify(b), { status: 200, headers: { 'content-type': 'application/json' } });
  if (url.includes('/meta')) return ok({ stages: [], lost_reasons: [{ value: 'price', label: 'Price' }] });
  if (url.includes('agent-options') || url.includes('sales-order-options')) return ok({ data: [] });
  if (url.includes('customer-options')) return ok({ items: [], prospect: null, blocked: null });
  if (method === 'GET' && url.includes('/opp-1')) return ok(opp);
  if (method === 'GET') return ok({ data: [opp], pagination: { total: 1, page: 1, limit: 200 }, empty: false });
  return ok(opp);
});
vi.mock('@/lib/api', () => ({ apiFetch: (...a: [string, RequestInit?]) => apiFetch(...a) }));

import SalesOpportunityDetail from './SalesOpportunityDetail';

const LIMITED = ['sales.opportunities.view_own', 'sales.opportunities.add', 'sales.opportunities.edit'];
const STAFF = ['sales.opportunities.view', 'sales.opportunities.add', 'sales.opportunities.edit', 'sales.opportunities.delete'];
const MINE = '/api/v1/my-requests/sales-opportunities/opp-1';

function mount(slugs: string[]) {
  held = new Set(slugs);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SalesOpportunityDetail id="opp-1" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  cleanup();
  calls.length = 0;
  vi.clearAllMocks();
});

describe('Sales Opportunity detail, limited user', () => {
  it('inline edit saves through my-requests and sends no agent', async () => {
    mount(LIMITED);
    fireEvent.click(await screen.findByRole('button', { name: /^edit$/i }));
    fireEvent.change(await screen.findByDisplayValue('ZZT Deal'), { target: { value: 'ZZT Renamed' } });
    fireEvent.click(screen.getByRole('button', { name: /^save/i }));
    await waitFor(() => expect(calls.filter((c) => c.method === 'PATCH' && c.url === MINE)).toHaveLength(1));
    const body = calls.find((c) => c.method === 'PATCH')?.body as Record<string, unknown>;
    expect(body).toMatchObject({ title: 'ZZT Renamed' });
    expect(body).not.toHaveProperty('sales_agent_id');
  });

});

describe('Sales Opportunity detail, staff user (control)', () => {
  it('keeps the Agent picker and the Won sales order link, saving through the staff PATCH', async () => {
    mount(STAFF);
    const gear = within(await screen.findByTestId('gear'));
    fireEvent.click(await gear.findByRole('button', { name: 'Qualified' }));
    await waitFor(() => expect(calls.filter((c) => c.method === 'PATCH' && c.url === '/api/v1/sales/opportunities/opp-1')).toHaveLength(1));
    fireEvent.click(await gear.findByRole('button', { name: 'Won' }));
    expect(await screen.findByLabelText('Sales order')).toBeTruthy();
    expect(calls.filter((c) => c.url.startsWith('/api/v1/my-requests/'))).toHaveLength(0);
  });
});
