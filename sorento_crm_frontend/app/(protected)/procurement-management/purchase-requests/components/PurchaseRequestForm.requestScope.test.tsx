/**
 * PORTAL-P4-REQUESTS S3 (P4-26): the Purchase Request / Sponsorship Form form for staff (control): no draft
 * buttons, the original Create, nothing sent to my-requests. Asserted at the HTTP seam (`apiFetch`). A LIMITED
 * user's form is the portal's own since R2 (PurchaseRequest.portalForm.test.tsx, SponsorshipForm.portalForm.test.tsx).
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const push = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => '/procurement-management/purchase-requests/new',
  useSearchParams: () => new URLSearchParams(window.location.search),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));
vi.mock('@/hooks/usePublicViewLinksEnabled', () => ({ usePublicViewLinksEnabled: () => false }));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
vi.mock('./PurchaseRequestAttachmentsSection', () => ({ __esModule: true, default: () => null }));
vi.mock('@/components/common/LookupBoundField', () => ({ __esModule: true, default: () => null }));
vi.mock('../services/purchaseRequestService', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  searchProjectsForLink: vi.fn().mockResolvedValue([]),
  getOrCreateViewLink: vi.fn(),
}));

let held = new Set<string>();
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => held.has(slug),
  useHasAnyPermission: (slugs: string[]) => slugs.some((s) => held.has(s)),
  usePermissions: () => ({ permissionSet: held, permissions: [...held], isLoading: false, isError: false }),
}));

// The picker: records that it loaded options, exposes its disabled state, picks one contact on click.
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (p: {
    fetchOptions?: (q: string) => Promise<unknown>;
    onChange: (v: string) => void;
    disabled?: boolean;
    value?: string;
    placeholder?: string;
  }) => {
    React.useEffect(() => {
      void p.fetchOptions?.('');
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);
    return (
      <button
        type="button"
        data-testid={p.fetchOptions ? 'requestor-picker' : `select-${p.placeholder ?? 'x'}`}
        data-disabled={String(!!p.disabled)}
        onClick={() => p.onChange('c1')}
      >
        {p.value ? `picked ${p.value}` : 'pick'}
      </button>
    );
  },
}));

type Kind = 'purchase_request' | 'sponsorship_form';
const KINDS: Array<{ kind: Kind; base: string; basePath: string }> = [
  { kind: 'purchase_request', base: 'procurement.purchase_requests', basePath: '/procurement-management/purchase-requests' },
  { kind: 'sponsorship_form', base: 'procurement.sponsorship_forms', basePath: '/procurement-management/sponsorship-forms' },
];

const calls: Array<{ url: string; method: string; body: unknown }> = [];
let sources: Record<string, Record<string, unknown>> = {};
const detail = (kind: Kind, over: Record<string, unknown> = {}) => ({
  id: 'pr-5',
  kind,
  request_type: kind,
  request_number: kind === 'purchase_request' ? 'PR26-0005' : 'SF26-0005',
  status: 'draft',
  approval_status: null,
  is_draft: true,
  is_editable: true,
  revision_no: 0,
  customer_name: 'OLD CUSTOMER',
  project_title: 'Old project',
  sales_type: 'project',
  purpose: 'old purpose',
  contact_id: 'c1',
  requested_by_contact_id: 'c1',
  requested_by_contact_name: 'Ann Sales',
  lines: [{ item_code: 'ITEM-A', quantity: 2, remark: null, unit_price: kind === 'sponsorship_form' ? 10 : null, total: kind === 'sponsorship_form' ? 20 : null }],
  attachments: [],
  revision: { enabled: false, allowed: false, used: 0, max: 0, remaining: 0, blocked_reason: null },
  ...over,
});

const apiFetch = vi.fn(async (url: string, init?: RequestInit) => {
  const method = (init?.method ?? 'GET').toUpperCase();
  let body: unknown = init?.body;
  if (typeof body === 'string') {
    try { body = JSON.parse(body); } catch { /* keep string */ }
  }
  calls.push({ url, method, body });
  const ok = (b: unknown) => new Response(JSON.stringify(b), { status: 200, headers: { 'content-type': 'application/json' } });
  if (url.startsWith('/api/v1/my-requests/requestor-options')) return ok({ items: [{ id: 'c1', name: 'Ann Sales' }], has_more: false });
  const mine = url.match(/^\/api\/v1\/my-requests\/submissions\/(purchase_request|sponsorship_form)(?:\/([^/?]+))?(\/submit|\/revise)?$/);
  if (mine) {
    const kind = mine[1] as Kind;
    const id = mine[2];
    if (method === 'GET' && id) return ok(sources[id] ?? detail(kind, { id }));
    if (mine[3] === '/submit') return ok(detail(kind, { id, status: 'submitted', is_draft: false }));
    if (mine[3] === '/revise') return ok({ submission: detail(kind, { id }), revision: {}, revision_no: 1 });
    return ok(detail(kind, { id: id ?? 'new-1' }));
  }
  const staffOne = url.match(/^\/api\/v1\/procurement\/purchase-requests\/([^/?]+)$/);
  if (staffOne && method === 'GET') return ok(sources[staffOne[1]] ?? detail('purchase_request', { id: staffOne[1] }));
  if (url.includes('requestor-select')) return ok({ items: [{ id: 'c1', name: 'Ann Sales' }], has_more: false });
  return ok({});
});
vi.mock('@/lib/api', () => ({ apiFetch: (...a: [string, RequestInit?]) => apiFetch(...a) }));

import PurchaseRequestForm from './PurchaseRequestForm';

const urls = (pred: (c: (typeof calls)[number]) => boolean) => calls.filter(pred);

function mount(k: (typeof KINDS)[number], slugs: string[], props: { requestId?: string } = {}, search = '') {
  held = new Set(slugs);
  window.history.pushState({}, '', `${k.basePath}/new${search}`);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <PurchaseRequestForm
        {...props}
        defaultRequestType={k.kind}
        expectedRequestType={k.kind}
        successRedirectUrl={k.basePath}
      />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  cleanup();
  calls.length = 0;
  sources = {};
  vi.clearAllMocks();
});

describe.each(KINDS)('$kind form, staff user /new (control, P4-26)', (k) => {
  it('shows Create, no draft buttons, and never touches my-requests', async () => {
    mount(k, [`${k.base}.view`, `${k.base}.add`, `${k.base}.edit`]);
    await screen.findByPlaceholderText('Project title');
    expect(screen.queryByRole('button', { name: 'Save as draft' })).toBeNull();
    expect(screen.queryByRole('button', { name: /^Submit/ })).toBeNull();
    expect(screen.getByRole('button', { name: /^Create$/ })).toBeInTheDocument();
    expect(urls((c) => c.url.startsWith('/api/v1/my-requests/'))).toHaveLength(0);
  });
});
