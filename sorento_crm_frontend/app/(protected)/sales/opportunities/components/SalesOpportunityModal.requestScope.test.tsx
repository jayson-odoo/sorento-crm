/**
 * PORTAL-P4-REQUESTS S6: the Log opportunity modal for a LIMITED user (`.view_own` + `.add`, never `.view`)
 * and for staff (control). Asserted at the HTTP seam (`apiFetch`):
 *  - limited: the customer search reads /api/v1/my-requests/sales-opportunities/customer-options (the agent's
 *    own customers) and Save POSTs /api/v1/my-requests/sales-opportunities; never the staff create route.
 *  - staff: unchanged (/api/v1/sales/opportunities, no my-requests).
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/sales/opportunities',
  useSearchParams: () => new URLSearchParams(),
}));
let held = new Set<string>();
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => held.has(slug),
  useHasAnyPermission: (slugs: string[]) => slugs.some((s) => held.has(s)),
  usePermissions: () => ({ permissionSet: held, permissions: [...held], isLoading: false, isError: false }),
}));

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    id?: string;
    'aria-label'?: string;
    value: string;
    onChange: (v: string) => void;
    onOptionChange?: (o: { value: string; label: string } | null) => void;
    options?: { value: string; label: string }[];
    fetchOptions?: (q: string, page: number) => Promise<{ value: string; label: string }[]>;
  }) => {
    const [options, setOptions] = React.useState(props.options ?? []);
    React.useEffect(() => {
      if (props.fetchOptions) void props.fetchOptions('', 0).then(setOptions);
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);
    const label = props['aria-label'] ?? props.id ?? 'select';
    return (
      <select
        aria-label={label}
        value={props.value}
        onChange={(e) => {
          props.onChange(e.target.value);
          props.onOptionChange?.(options.find((o) => o.value === e.target.value) ?? null);
        }}
      >
        <option value="" />
        {options.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    );
  },
}));

const calls: Array<{ url: string; method: string; body: unknown }> = [];
const apiFetch = vi.fn(async (url: string, init?: RequestInit) => {
  const method = (init?.method ?? 'GET').toUpperCase();
  let body: unknown = init?.body;
  if (typeof body === 'string') {
    try { body = JSON.parse(body); } catch { /* keep */ }
  }
  calls.push({ url, method, body });
  const ok = (b: unknown) => new Response(JSON.stringify(b), { status: 200, headers: { 'content-type': 'application/json' } });
  if (url.includes('customer-options')) {
    return ok({ items: [{ customer_id: 'cust-1', customer_code: 'C1', customer_name: 'ZZT Mine', label: 'C1 - ZZT Mine' }], prospect: { name: 'ZZT Fresh Prospect' }, blocked: null });
  }
  if (method === 'POST') return ok({ id: 'opp-new' });
  return ok({});
});
vi.mock('@/lib/api', () => ({ apiFetch: (...a: [string, RequestInit?]) => apiFetch(...a) }));

import SalesOpportunityModal from './SalesOpportunityModal';

const LIMITED = ['sales.opportunities.view_own', 'sales.opportunities.add', 'sales.opportunities.edit'];
const STAFF = ['sales.opportunities.view', 'sales.opportunities.add', 'sales.opportunities.edit'];
const MINE = '/api/v1/my-requests/sales-opportunities';

function mount(slugs: string[]) {
  held = new Set(slugs);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SalesOpportunityModal open onOpenChange={() => {}} />
    </QueryClientProvider>,
  );
}

async function fillAndSave() {
  const title = await screen.findByLabelText(/^Title/);
  fireEvent.change(title, { target: { value: 'ZZT Deal' } });
  const customer = screen.getByLabelText('Customer or prospect');
  await waitFor(() => expect((customer as HTMLSelectElement).options.length).toBeGreaterThan(1));
  fireEvent.change(customer, { target: { value: (customer as HTMLSelectElement).options[1].value } });
  const date = document.querySelector('input[type="date"]') as HTMLInputElement | null;
  if (date) fireEvent.change(date, { target: { value: '2026-12-01' } });
  const amount = screen.queryByLabelText(/Expected amount/i);
  if (amount) fireEvent.change(amount, { target: { value: '500' } });
  fireEvent.click(screen.getByRole('button', { name: /^(Log opportunity|Save|Create)/i }));
}

beforeEach(() => {
  cleanup();
  calls.length = 0;
  vi.clearAllMocks();
});

describe('Sales Opportunity modal, limited user', () => {
  it('searches customers through my-requests (the agent\'s own) and never the staff options route', async () => {
    mount(LIMITED);
    await waitFor(() => expect(calls.filter((c) => c.url.startsWith(`${MINE}/customer-options`)).length).toBeGreaterThan(0));
    expect(calls.filter((c) => c.url.startsWith('/api/v1/sales/opportunities/customer-options'))).toHaveLength(0);
  });

  it('Save POSTs /api/v1/my-requests/sales-opportunities with the portal body (no agent) and never the staff create', async () => {
    mount(LIMITED);
    await fillAndSave();
    await waitFor(() => expect(calls.filter((c) => c.method === 'POST' && c.url === MINE)).toHaveLength(1));
    const body = calls.find((c) => c.method === 'POST')?.body as Record<string, unknown>;
    expect(body).toMatchObject({ title: 'ZZT Deal' });
    expect(body).not.toHaveProperty('sales_agent_id');
    expect(calls.filter((c) => c.url === '/api/v1/sales/opportunities' && c.method === 'POST')).toHaveLength(0);
  });
});

describe('Sales Opportunity modal, staff user (control)', () => {
  it('Save still POSTs the staff route and never touches my-requests', async () => {
    mount(STAFF);
    await fillAndSave();
    await waitFor(() => expect(calls.filter((c) => c.method === 'POST' && c.url === '/api/v1/sales/opportunities')).toHaveLength(1));
    expect(calls.filter((c) => c.url.startsWith('/api/v1/my-requests/'))).toHaveLength(0);
  });
});
