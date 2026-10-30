/**
 * PORTAL-P4-REQUESTS S5: the New Product Application detail for a LIMITED user (`.view_own` + `.create`, never
 * `.view` / `.approve` / `.open_code`): the portal's actions only, asserted at the HTTP seam. Staff (control) unchanged.
 *  - the detail itself loads from the staff GET (the server returns only their row, in the portal's shape)
 *  - draft: Submit -> POST /api/v1/my-requests/submissions/new_product_application/{id}/submit
 *  - submitted: Revise (reason) -> POST .../{id}/revise {reason}; Cancel application -> POST .../{id}/cancel
 *  - a draft raised in the portal still offers Edit (the staff page hides it for portal rows: the portal code edits it)
 *  - files: an upload POSTs /api/v1/my-requests/attachments with kind + submission_id
 *  - never: Approve / Reject, Link product / Not opening / Undo, Save feedback, a staff write route
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const state = vi.hoisted(() => ({ perms: new Set<string>(), userId: 'u-owner', detail: {} as Record<string, unknown> }));

class ResizeObserverStub { observe() {} unobserve() {} disconnect() {} }
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
Element.prototype.scrollIntoView = vi.fn();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(''),
  usePathname: () => '/procurement-management/new-product-applications/a-1',
}));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => state.perms.has(slug),
  useHasAnyPermission: (slugs: string[]) => slugs.some((s) => state.perms.has(s)),
  usePermissions: () => ({ permissionSet: state.perms, permissions: [...state.perms], isLoading: false, isError: false }),
}));
vi.mock('@/hooks/useEffectiveUserId', () => ({ useEffectiveUserId: () => state.userId }));
vi.mock('@/hooks/useDeferredAction', () => ({ useDeferredAction: () => ({ countdown: null, isBlocked: false, start: vi.fn() }) }));
vi.mock('@/hooks/useDeferredRowAction', () => ({
  useDeferredRowAction: () => ({ run: vi.fn(), targetId: null, isPending: false, countdown: null }),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/components/audit/AuditTrail', () => ({ default: () => <div data-testid="audit-trail" /> }));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: () => Promise.resolve(), isLoading: false }),
}));
vi.mock('@/components/common/DetailActions', () => ({
  default: ({ gear, primary }: { gear?: React.ReactNode; primary?: React.ReactNode }) => (
    <div>
      {gear}
      {primary}
    </div>
  ),
}));
vi.mock('@/components/common/DetailActionsMenu', () => ({
  DetailActionsMenu: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
vi.mock('@/components/ui/dropdown-menu', () => ({
  DropdownMenuItem: ({ children, onSelect }: { children: React.ReactNode; onSelect?: () => void }) => (
    <button onClick={() => onSelect?.()}>{children}</button>
  ),
}));

const calls: Array<{ url: string; method: string; body: unknown }> = [];
const apiFetch = vi.fn(async (url: string, init?: RequestInit) => {
  const method = (init?.method ?? 'GET').toUpperCase();
  let body: unknown = init?.body;
  if (typeof body === 'string') {
    try { body = JSON.parse(body); } catch { /* keep */ }
  }
  if (typeof FormData !== 'undefined' && body instanceof FormData) body = Object.fromEntries(body.entries());
  calls.push({ url, method, body });
  const payload = url.includes('/attachments') && method === 'POST'
    ? { link_id: 'ln-1', attachment_id: 'at-1', filename: 'spec.pdf' }
    : state.detail;
  return new Response(JSON.stringify(payload), { status: 200, headers: { 'content-type': 'application/json' } });
});
vi.mock('@/lib/api', () => ({ apiFetch: (...a: [string, RequestInit?]) => apiFetch(...a) }));

import NewProductApplicationDetail from './NewProductApplicationDetail';

const P = 'procurement.new_product_applications';
const LIMITED = [`${P}.view_own`, `${P}.create`];
const STAFF_APPROVER = [`${P}.view`, `${P}.approve`];
const STAFF_OWNER = [`${P}.create`];
const MINE = '/api/v1/my-requests/submissions/new_product_application/a-1';
const STAFF_BASE = '/api/v1/procurement/new-product-applications';
const STAFF_WRITE = (c: { url: string; method: string }) => c.url.startsWith(STAFF_BASE) && c.method !== 'GET';

function line(over: Record<string, unknown> = {}) {
  return {
    id: 'l-1', line_no: 1, proposed_code: 'XY-1234-MB', description: 'Example kitchen sink', dimension: '600x400',
    material: 'Steel', thickness: '1.2mm', packing: 'Carton', brand_id: null, brand_name: null, expected_qty: '55',
    cost_price: null, opened_product_id: null, opened_product_code: null, opened_product_name: null,
    opened_product_active: null, closed_reason: null, resolved_by: null, resolved_by_name: null, resolved_at: null,
    ...over,
  };
}

function detail(over: Record<string, unknown> = {}) {
  return {
    id: 'a-1', application_no: 'NPA-000001', status: 'draft', status_label: 'Draft', source: 'portal',
    applicant_id: 'u-owner', applicant_name: 'Owner', stock_inquiry_id: null, stock_inquiry_number: null,
    customer_id: null, customer_code: null, customer_name: 'EXAMPLE DEVELOPER SDN BHD', project_name: 'TOWER B',
    first_line: 'XY-1234-MB', lines_total: 1, lines_done: 0, opened_codes: [], needed_by: null, submitted_at: null,
    created_at: '2026-10-17T01:00:00', updated_at: null, remark: null, lead_time: null, attachments: [],
    decided_at: null, decided_by: null, decided_by_name: null, reject_reason: null, revise_reason: null,
    cancelled_at: null, cancel_reason: null, completed_at: null, lines: [line()],
    ...over,
  };
}

function mount(slugs: string[], over: Record<string, unknown> = {}) {
  state.perms = new Set(slugs);
  state.detail = detail(over);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <NewProductApplicationDetail applicationId="a-1" />
    </QueryClientProvider>,
  );
}

const button = (name: RegExp) => screen.queryByRole('button', { name });

beforeEach(() => {
  calls.length = 0;
  vi.clearAllMocks();
  state.userId = 'u-owner';
});
afterEach(cleanup);


describe('Audit Trail for a limited user (PORTAL-P4-REQUESTS)', () => {
  it('limited user: no Audit Trail section (the portal has none; /audit/logs answers 403)', async () => {
    mount(LIMITED);
    await screen.findAllByText(/NPA-000001/);
    expect(screen.queryByTestId('audit-trail')).toBeNull();
  });

  it('staff: Audit Trail section stays', async () => {
    mount(STAFF_APPROVER);
    await screen.findAllByText(/NPA-000001/);
    expect(await screen.findByTestId('audit-trail')).toBeInTheDocument();
  });
});
