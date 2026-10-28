/**
 * PORTAL-P4-REQUESTS S5: the New Product Application form for a LIMITED user (holds `.view_own`, not `.view`) and for
 * staff (control). Asserted at the HTTP seam (`apiFetch`) so it holds however the coder splits hooks:
 *  - limited /new: "Save as draft" -> POST /api/v1/my-requests/submissions/new_product_application; edit -> PUT .../{id};
 *    "Submit" saves, then POST .../{id}/submit; never the staff write routes under /api/v1/procurement/new-product-applications.
 *  - "start from": ?stock_inquiry_id= reads /api/v1/my-requests/new-product-application/prefill.
 *  - the Customer picker reads /api/v1/my-requests/new-product-application/customers (the agent's own customers).
 *  - the stock-inquiry picker reads /api/v1/my-requests/new-product-application/inquiries (own responded ones).
 *  - staff keeps POST /api/v1/procurement/new-product-applications and never touches my-requests.
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const push = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => '/procurement-management/new-product-applications/new',
  useSearchParams: () => new URLSearchParams(''),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() } }));

let held = new Set<string>();
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => held.has(slug),
  useHasAnyPermission: (slugs: string[]) => slugs.some((s) => held.has(s)),
  usePermissions: () => ({ permissionSet: held, permissions: [...held], isLoading: false, isError: false }),
}));
vi.mock('@/hooks/useDeferredRowAction', () => ({
  useDeferredRowAction: () => ({ run: vi.fn(), targetId: null, isPending: false, countdown: null }),
}));
vi.mock('@/hooks/useDeferredAction', () => ({ useDeferredAction: () => ({ countdown: null, isBlocked: false, start: vi.fn() }) }));
vi.mock('@/app/(protected)/master-data-management/shared/hooks/use-brand-select-query', () => ({
  useBrandSelectQuery: () => ({ data: [] }),
}));

const calls: Array<{ url: string; method: string; body: unknown }> = [];
const detail = (over: Record<string, unknown> = {}) => ({
  id: 'npa-5', application_no: 'NPA-000005', status: 'draft', status_label: 'Draft', source: 'portal',
  applicant_id: 'u-owner', applicant_name: 'Owner', stock_inquiry_id: null, stock_inquiry_number: null,
  customer_id: null, customer_code: null, customer_name: 'Typed Co', project_name: 'Typed project', needed_by: null,
  remark: null, lead_time: null, attachments: [], created_at: '2026-10-10T01:00:00', submitted_at: null,
  lines: [{ id: 'l-1', line_no: 1, proposed_code: 'XY-1', description: 'Sink', dimension: null, material: null, thickness: null,
    packing: null, brand_id: null, brand_name: null, expected_qty: '5', cost_price: null, opened_product_id: null,
    closed_reason: null }],
  ...over,
});
const PREFILL = {
  stock_inquiry_id: 'si-1', stock_inquiry_number: 'SI26-0412', customer_id: null, customer_name: 'EXAMPLE DEVELOPER',
  project_name: 'EXAMPLE RESIDENCE', needed_by: null, remark: null,
  lines: [{ proposed_code: 'XY-1234-MB', description: 'Example sinks', expected_qty: '55' }],
};
const apiFetch = vi.fn(async (url: string, init?: RequestInit) => {
  const method = (init?.method ?? 'GET').toUpperCase();
  let body: unknown = init?.body;
  if (typeof body === 'string') {
    try { body = JSON.parse(body); } catch { /* keep */ }
  }
  calls.push({ url, method, body });
  const ok = (b: unknown) => new Response(JSON.stringify(b), { status: 200, headers: { 'content-type': 'application/json' } });
  if (url.includes('/prefill')) return ok(PREFILL);
  if (url.includes('/customers') || url.includes('/inquiries') || url.includes('/lookups/') || url.includes('stock-inquiries')) {
    return ok(url.includes('stock-inquiries') ? { data: [] } : []);
  }
  if (/\/new-product-applications?\/?$/.test(url) || /submissions\/new_product_application\/?$/.test(url)) return ok(detail({ id: 'new-1' }));
  return ok(detail());
});
vi.mock('@/lib/api', () => ({ apiFetch: (...a: [string, RequestInit?]) => apiFetch(...a) }));

import NewProductApplicationForm from './NewProductApplicationForm';

const LIMITED = ['procurement.new_product_applications.view_own', 'procurement.new_product_applications.create'];
const STAFF = ['procurement.new_product_applications.view', 'procurement.new_product_applications.create'];
const MINE = '/api/v1/my-requests/submissions/new_product_application';
const OWN = '/api/v1/my-requests/new-product-application';
const STAFF_BASE = '/api/v1/procurement/new-product-applications';
const where = (pred: (c: (typeof calls)[number]) => boolean) => calls.filter(pred);
const STAFF_WRITE = (c: { url: string; method: string }) => c.url.startsWith(STAFF_BASE) && c.method !== 'GET';

function mount(slugs: string[], props: { applicationId?: string; stockInquiryId?: string } = {}) {
  held = new Set(slugs);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <NewProductApplicationForm {...props} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  cleanup();
  calls.length = 0;
  vi.clearAllMocks();
});

describe('New Product Application form, limited user', () => {
  it('"Save as draft" POSTs through my-requests and never the staff create route', async () => {
    mount(LIMITED);
    fireEvent.click(await screen.findByRole('button', { name: 'Save as draft' }));
    await waitFor(() => expect(where((c) => c.method === 'POST' && c.url === MINE)).toHaveLength(1));
    expect(where(STAFF_WRITE)).toHaveLength(0);
  });

  it('editing a draft (even one raised in the portal) saves through PUT my-requests/.../{id}', async () => {
    mount(LIMITED, { applicationId: 'npa-5' });
    fireEvent.click(await screen.findByRole('button', { name: 'Save as draft' }));
    await waitFor(() => expect(where((c) => c.method === 'PUT' && c.url === `${MINE}/npa-5`)).toHaveLength(1));
    expect(where(STAFF_WRITE)).toHaveLength(0);
  });

  it('"Submit" saves, then POSTs my-requests .../submit, never the staff submit', async () => {
    mount(LIMITED, { applicationId: 'npa-5' });
    fireEvent.click(await screen.findByRole('button', { name: 'Submit' }));
    await waitFor(() => expect(where((c) => c.method === 'POST' && c.url === `${MINE}/npa-5/submit`)).toHaveLength(1));
    expect(where(STAFF_WRITE)).toHaveLength(0);
  });

  it('"start from" an inquiry reads the prefill through my-requests, not the staff prefill', async () => {
    mount(LIMITED, { stockInquiryId: 'si-1' });
    await waitFor(() => expect(where((c) => c.url.startsWith(`${OWN}/prefill`) && c.url.includes('stock_inquiry_id=si-1'))).toHaveLength(1));
    expect(where((c) => c.url.startsWith(`${STAFF_BASE}/prefill`))).toHaveLength(0);
  });

  it('the Customer picker is the agent\'s own customers (my-requests), never the staff customer lookup', async () => {
    mount(LIMITED);
    await screen.findByRole('button', { name: 'Save as draft' });
    const input = screen.getByLabelText('Customer');
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: 'Ko' } });
    await waitFor(() => expect(where((c) => c.url.startsWith(`${OWN}/customers`)).length).toBeGreaterThan(0));
    expect(where((c) => c.url.includes('/purchase-requests/') && c.url.includes('customer'))).toHaveLength(0);
  });

  it('the stock-inquiry picker lists the contact\'s own responded inquiries (my-requests), not the staff inquiry list', async () => {
    mount(LIMITED);
    await screen.findByRole('button', { name: 'Save as draft' });
    fireEvent.click(screen.getByLabelText('Stock inquiry'));
    await waitFor(() => expect(where((c) => c.url.startsWith(`${OWN}/inquiries`)).length).toBeGreaterThan(0));
    expect(where((c) => c.url.startsWith('/api/v1/procurement/stock-inquiries'))).toHaveLength(0);
  });
});

describe('New Product Application form, staff user (control)', () => {
  it('"Save as draft" still POSTs the staff route and never touches my-requests', async () => {
    mount(STAFF);
    fireEvent.click(await screen.findByRole('button', { name: 'Save as draft' }));
    await waitFor(() => expect(where((c) => c.method === 'POST' && c.url === STAFF_BASE)).toHaveLength(1));
    expect(where((c) => c.url.startsWith('/api/v1/my-requests/'))).toHaveLength(0);
  });

  it('a create-only applicant (no view_own) is staff too: staff route', async () => {
    mount(['procurement.new_product_applications.create']);
    fireEvent.click(await screen.findByRole('button', { name: 'Save as draft' }));
    await waitFor(() => expect(where((c) => c.method === 'POST' && c.url === STAFF_BASE)).toHaveLength(1));
    expect(where((c) => c.url.startsWith('/api/v1/my-requests/'))).toHaveLength(0);
  });

  it('the pickers still read the staff lookups (the gesture used above reaches them)', async () => {
    mount(STAFF);
    await screen.findByRole('button', { name: 'Save as draft' });
    fireEvent.click(screen.getByLabelText('Stock inquiry'));
    const input = screen.getByLabelText('Customer');
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: 'Ko' } });
    await waitFor(() => expect(where((c) => c.url.startsWith('/api/v1/procurement/stock-inquiries')).length).toBeGreaterThan(0));
    expect(where((c) => c.url.startsWith('/api/v1/my-requests/'))).toHaveLength(0);
  });
});
