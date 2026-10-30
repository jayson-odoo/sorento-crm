/**
 * PORTAL-P4-REQUESTS S2 (P4-24, P4-14, P4-26): the Complaint form for a LIMITED user (holds `.view_own`, not
 * `.view`) and for staff (control). Asserted at the HTTP seam (`apiFetch`) so it holds however the coder splits hooks:
 *  - limited /new: no "Technical Team" card (contact id, space id, root cause, resolution, technical response);
 *    "Save as draft" -> POST /api/v1/my-requests/submissions/complaint (then PUT .../{id}); "Submit" -> POST .../{id}/submit.
 *  - `?from=<id>` pre-fills a NEW draft from GET /api/v1/my-requests/submissions/complaint/<id> (Duplicate).
 *  - edit: only draft / rejected rows are editable; `?revise=1` on a revisable row shows the reason box
 *    (`id="revision_reason"`) and "Send revision" -> POST .../{id}/revise.
 *  - staff /new: no draft buttons, the Technical Team card present, nothing sent to my-requests.
 * Modelled on StockInquiryForm.requestScope.test.tsx.
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const push = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => '/complaint-management/complaints/new',
  useSearchParams: () => new URLSearchParams(window.location.search),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));
vi.mock('@/hooks/usePublicViewLinksEnabled', () => ({ usePublicViewLinksEnabled: () => false }));
vi.mock('./ComplaintManualAttachmentsSection', () => ({ __esModule: true, default: () => null }));
vi.mock('@/components/common/ListPager', () => ({ __esModule: true, default: () => null }));
vi.mock('@/components/common/LookupBoundField', () => ({ __esModule: true, default: () => null }));
vi.mock('@/app/(protected)/complaint-management/complaint-root-causes/hooks/useComplaintRootCauses', () => ({
  useComplaintRootCausesSelect: () => ({ data: [], error: null, refetch: vi.fn() }),
}));
vi.mock('@/app/(protected)/complaint-management/complaint-resolutions/hooks/useComplaintResolutions', () => ({
  useComplaintResolutionsSelect: () => ({ data: [], error: null, refetch: vi.fn() }),
}));

let held = new Set<string>();
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => held.has(slug),
  useHasAnyPermission: (slugs: string[]) => slugs.some((s) => held.has(s)),
  usePermissions: () => ({ permissionSet: held, permissions: [...held], isLoading: false, isError: false }),
}));
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: () => <span data-testid="select-stub" />,
}));

const calls: Array<{ url: string; method: string; body: unknown }> = [];
const detail = (over: Record<string, unknown> = {}) => ({
  id: 'cp-5',
  kind: 'complaint',
  status: 'draft',
  is_draft: true,
  is_editable: true,
  revision_no: 0,
  customer_name: 'OLD CUSTOMER',
  defect_description: 'old defect',
  delivery_order_number: 'DO-OLD',
  product_lines: [],
  attachments: [],
  revision: { enabled: false, allowed: false, used: 0, max: 0, remaining: 0, blocked_reason: null },
  ...over,
});
let sources: Record<string, Record<string, unknown>> = {};

const apiFetch = vi.fn(async (url: string, init?: RequestInit) => {
  const method = (init?.method ?? 'GET').toUpperCase();
  let body: unknown = init?.body;
  if (typeof body === 'string') {
    try { body = JSON.parse(body); } catch { /* keep string */ }
  }
  calls.push({ url, method, body });
  const ok = (b: unknown) => new Response(JSON.stringify(b), { status: 200, headers: { 'content-type': 'application/json' } });
  const mine = url.match(/^\/api\/v1\/my-requests\/submissions\/complaint(?:\/([^/?]+))?(\/submit|\/revise)?$/);
  if (mine) {
    const id = mine[1];
    if (method === 'GET' && id) return ok(sources[id] ?? detail({ id }));
    if (mine[2] === '/submit') return ok(detail({ id, status: 'submitted', is_draft: false }));
    if (mine[2] === '/revise') return ok({ submission: detail({ id }), revision: {}, revision_no: 1 });
    return ok(detail({ id: id ?? 'new-1' }));
  }
  const staffOne = url.match(/^\/api\/v1\/complaints-management\/complaints\/([^/?]+)$/);
  if (staffOne && method === 'GET') return ok(sources[staffOne[1]] ?? detail({ id: staffOne[1] }));
  return ok({});
});
vi.mock('@/lib/api', () => ({ apiFetch: (...a: [string, RequestInit?]) => apiFetch(...a) }));

import ComplaintForm from './ComplaintForm';

const STAFF = [
  'complaint_management.complaints.view',
  'complaint_management.complaints.add',
  'complaint_management.complaints.edit',
];
const urls = (pred: (c: (typeof calls)[number]) => boolean) => calls.filter(pred);

function mount(slugs: string[], props: { complaintId?: string } = {}, search = '') {
  held = new Set(slugs);
  window.history.pushState({}, '', `/complaint-management/complaints/new${search}`);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ComplaintForm {...props} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  cleanup();
  calls.length = 0;
  sources = {};
  vi.clearAllMocks();
});

// PORTAL-P4-REQUESTS R1: a limited user now gets the portal's own form; its cases live in Complaint.portalForm.test.tsx and the portal's own SubmissionForm tests.



describe('staff user, /new (control, P4-26)', () => {
  it('keeps the Technical Team card, shows no draft buttons, and never touches my-requests', async () => {
    mount(STAFF);
    await screen.findByPlaceholderText('Enter customer name');
    expect(screen.getByPlaceholderText('Respond.io contact ID')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Enter technical team response to send to customer')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Save as draft' })).toBeNull();
    expect(screen.queryByRole('button', { name: /^Submit/ })).toBeNull();
    expect(screen.getByRole('button', { name: 'Create Complaint' })).toBeInTheDocument();
    expect(urls((c) => c.url.startsWith('/api/v1/my-requests/'))).toHaveLength(0);
  });
});
