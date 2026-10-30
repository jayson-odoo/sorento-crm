/**
 * PORTAL-P4-REQUESTS S4: the Sample Request detail for a LIMITED user (`.view_own` + `.create`, never `.view`
 * or `.process`): the portal's actions only. Asserted at the HTTP seam. Staff (control) is unchanged.
 *  - draft: Submit -> POST /api/v1/my-requests/submissions/sample_request/{id}/submit
 *  - draft or submitted: Cancel request -> POST .../{id}/cancel (never the staff /move)
 *  - never: Change to processing, Set consignment / PO no, the consignment / PO fields
 *  - the detail itself still loads from the staff GET (the server returns only their own row)
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const state = vi.hoisted(() => ({ perms: new Set<string>(), userId: 'u-owner', detail: {} as Record<string, unknown> }));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(''),
  usePathname: () => '/project-sales/sample-requests/r-1',
}));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => state.perms.has(slug),
  useHasAnyPermission: (slugs: string[]) => slugs.some((s) => state.perms.has(s)),
  usePermissions: () => ({ permissionSet: state.perms, permissions: [...state.perms], isLoading: false, isError: false }),
}));
vi.mock('@/hooks/useEffectiveUserId', () => ({ useEffectiveUserId: () => state.userId }));
vi.mock('@/hooks/useDeferredAction', () => ({ useDeferredAction: () => ({ countdown: null, isBlocked: false, start: vi.fn() }) }));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/components/audit/AuditTrail', () => ({ default: () => <div data-testid="audit-trail" /> }));
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
vi.mock('../../_shared/components/OrderInquiryStockGrid', () => ({ OrderInquiryStockGrid: () => <div /> }));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: () => Promise.resolve(), isLoading: false }),
}));

const calls: Array<{ url: string; method: string }> = [];
const apiFetch = vi.fn(async (url: string, init?: RequestInit) => {
  const method = (init?.method ?? 'GET').toUpperCase();
  calls.push({ url, method });
  const body = method === 'GET' && /sample-requests\/r-1$/.test(url) ? state.detail : state.detail;
  return new Response(JSON.stringify(body), { status: 200, headers: { 'content-type': 'application/json' } });
});
vi.mock('@/lib/api', () => ({ apiFetch: (...a: [string, RequestInit?]) => apiFetch(...a) }));

import SampleRequestDetail from './SampleRequestDetail';

const LIMITED = ['projects.sample_requests.view_own', 'projects.sample_requests.create'];
const STAFF_PROCESS = ['projects.sample_requests.view', 'projects.sample_requests.process', 'projects.sample_requests.create'];
const MINE = '/api/v1/my-requests/submissions/sample_request/r-1';

function detail(over: Record<string, unknown> = {}) {
  return {
    id: 'r-1', request_no: 'SR-000001', status: 'draft', status_label: 'Draft', source: 'portal',
    salesperson_id: 'u-owner', salesperson_name: 'Owner', customer_id: 'c-1', customer_code: 'D-001',
    customer_name: 'Acme Sdn Bhd', project_id: null, project_code: null, project_name: null,
    consignment_no: 'CN-77', po_no: 'PO-88', created_at: '2026-10-10T01:00:00',
    lines: [{ id: 'l-1', line_no: 1, product_id: 'p-1', product_code: 'TILE-1', product_name: 'Tile', brand_name: 'B', product_active: true, qty: 2, remark: null }],
    ...over,
  };
}

function mount(slugs: string[], over: Record<string, unknown> = {}) {
  state.perms = new Set(slugs);
  state.detail = detail(over);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SampleRequestDetail requestId="r-1" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  calls.length = 0;
  vi.clearAllMocks();
});
afterEach(cleanup);

describe('Sample Request detail, limited user', () => {
  it.each(['submitted'])('Cancel request on a %s row POSTs .../cancel, not the staff move', async (status) => {
    mount(LIMITED, { status, status_label: status });
    fireEvent.click(await screen.findByText('Cancel request'));
    await waitFor(() => expect(calls.filter((c) => c.method === 'POST' && c.url === `${MINE}/cancel`)).toHaveLength(1));
    expect(calls.filter((c) => c.url.endsWith('/move'))).toHaveLength(0);
  });

  it('shows no process move, no consignment / PO action and no consignment / PO fields', async () => {
    mount(LIMITED, { status: 'submitted', status_label: 'Submitted' });
    await screen.findByText('Cancel request');
    expect(screen.queryByText('Change to processing')).toBeNull();
    expect(screen.queryByText(/Set consignment/)).toBeNull();
    const text = document.body.textContent ?? '';
    expect(text).not.toMatch(/Consignment No/);
    expect(text).not.toMatch(/PO No/);
    expect(text).not.toContain('CN-77');
    expect(text).not.toContain('PO-88');
  });

});

describe('Sample Request detail, staff user (control)', () => {
  it('a process holder still sees Change to processing and the consignment / PO fields', async () => {
    mount(STAFF_PROCESS, { status: 'submitted', status_label: 'Submitted' });
    expect(await screen.findByText('Change to processing')).toBeTruthy();
    expect(screen.getByText(/Set consignment/)).toBeTruthy();
    expect(document.body.textContent).toMatch(/Consignment No/);
  });
});
