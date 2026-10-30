/**
 * PORTAL-P4-REQUESTS S4: the Sample Request form for a LIMITED user (holds `.view_own`, not `.view`) and for
 * staff (control). Asserted at the HTTP seam (`apiFetch`) so it holds however the coder splits hooks:
 *  - limited /new: "Save as draft" -> POST /api/v1/my-requests/submissions/sample_request (body = the portal's
 *    SampleRequestWrite); edit -> PUT .../{id}; never the staff write routes under /api/v1/project-sales.
 *  - the customer picker reads /api/v1/my-requests/sample-request/customers (the agent's own customers).
 *  - staff keeps POST /api/v1/project-sales/sample-requests and never touches my-requests.
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const push = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => '/project-sales/sample-requests/new',
  useSearchParams: () => new URLSearchParams(''),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() } }));

let held = new Set<string>();
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => held.has(slug),
  useHasAnyPermission: (slugs: string[]) => slugs.some((s) => held.has(s)),
  usePermissions: () => ({ permissionSet: held, permissions: [...held], isLoading: false, isError: false }),
}));

const calls: Array<{ url: string; method: string; body: unknown }> = [];
const detail = (over: Record<string, unknown> = {}) => ({
  id: 'sr-5',
  request_no: 'SR-000005',
  status: 'draft',
  status_label: 'Draft',
  source: 'portal',
  customer_id: null,
  customer_name: 'Typed Co',
  project_id: null,
  project_title: 'Typed project',
  delivery_date: '2026-12-01',
  delivery_mode: 'driver',
  ship_to_name: 'Site',
  lines: [],
  ...over,
});
const apiFetch = vi.fn(async (url: string, init?: RequestInit) => {
  const method = (init?.method ?? 'GET').toUpperCase();
  let body: unknown = init?.body;
  if (typeof body === 'string') {
    try { body = JSON.parse(body); } catch { /* keep */ }
  }
  calls.push({ url, method, body });
  const ok = (b: unknown) => new Response(JSON.stringify(b), { status: 200, headers: { 'content-type': 'application/json' } });
  if (url.includes('/sample-request/customers') || url.includes('customer')) return ok([]);
  if (/sample-requests?\/?(\?|$)/.test(url) || /submissions\/sample_request\/?$/.test(url)) return ok(detail({ id: 'new-1' }));
  if (/sample-requests?\/sr-5|submissions\/sample_request\/sr-5/.test(url)) return ok(detail());
  return ok({});
});
vi.mock('@/lib/api', () => ({ apiFetch: (...a: [string, RequestInit?]) => apiFetch(...a) }));

import SampleRequestForm from './SampleRequestForm';

const LIMITED = ['projects.sample_requests.view_own', 'projects.sample_requests.create'];
const STAFF = ['projects.sample_requests.view', 'projects.sample_requests.create'];
const where = (pred: (c: (typeof calls)[number]) => boolean) => calls.filter(pred);
const MINE = '/api/v1/my-requests/submissions/sample_request';
const STAFF_WRITE = (c: { url: string; method: string }) => c.url.startsWith('/api/v1/project-sales/sample-requests') && c.method !== 'GET';

function mount(slugs: string[], props: { requestId?: string } = {}) {
  held = new Set(slugs);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SampleRequestForm {...props} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  cleanup();
  calls.length = 0;
  vi.clearAllMocks();
});

describe('Sample Request form, limited user', () => {
  it('"Save as draft" POSTs through my-requests and never the staff create route', async () => {
    mount(LIMITED);
    fireEvent.click(await screen.findByRole('button', { name: 'Save as draft' }));
    await waitFor(() => expect(where((c) => c.method === 'POST' && c.url === MINE)).toHaveLength(1));
    expect(where(STAFF_WRITE)).toHaveLength(0);
  });

  it('editing a draft saves through PUT my-requests/.../{id}', async () => {
    mount(LIMITED, { requestId: 'sr-5' });
    fireEvent.click(await screen.findByRole('button', { name: 'Save as draft' }));
    await waitFor(() => expect(where((c) => c.method === 'PUT' && c.url === `${MINE}/sr-5`)).toHaveLength(1));
    expect(where(STAFF_WRITE)).toHaveLength(0);
  });

  it('the customer picker is the agent\'s own customers (my-requests), never the staff customer lookup', async () => {
    mount(LIMITED);
    await screen.findByRole('button', { name: 'Save as draft' });
    fireEvent.focus(screen.getByLabelText(/^Customer Name/));
    fireEvent.change(screen.getByLabelText(/^Customer Name/), { target: { value: 'Ko' } });
    await waitFor(() => expect(where((c) => c.url.startsWith('/api/v1/my-requests/sample-request/customers')).length).toBeGreaterThan(0));
    expect(where((c) => c.url.includes('/procurement/') && c.url.includes('customer'))).toHaveLength(0);
  });
});

describe('Sample Request form, staff user (control)', () => {
  it('"Save as draft" still POSTs the staff route and never touches my-requests', async () => {
    mount(STAFF);
    fireEvent.click(await screen.findByRole('button', { name: 'Save as draft' }));
    await waitFor(() => expect(where((c) => c.method === 'POST' && c.url === '/api/v1/project-sales/sample-requests')).toHaveLength(1));
    expect(where((c) => c.url.startsWith('/api/v1/my-requests/'))).toHaveLength(0);
  });
});
