/**
 * SPARE-PART-OR-B (slice 2 of #2381), red-first (Phase 2). The OR record page.
 * Contract: documentation/plans/purchasing/spare-part-or-b-14nov-acceptance-criteria.md.
 *
 * U3.2 The OR page Lines tab carries the "OI" column (the OR view of the spare part columns),
 *      linking the line to its OI row; it has no "Order request" column (that is the OI view).
 * U3.4 The OR page header title stays the OR- number even when the request has an oi_no.
 * U4.6 The OR status pill shows the revision state (Draft / Pending approval / Rejected)
 *      while a revision is open (`revision_state`), else the header state.
 *
 * NAMED CONTRACT CHOICES:
 * 1. SparePartRequestRecord passes `sparePart.view = 'request'` to OrderInquiryLinesTab,
 *    which threads it as `sparePartView` to `useOrderInquiryHeaderLinesColumns`
 *    (orderInquiryHeaderLinesColumns.orB.test.tsx pins the columns themselves).
 * 2. The request detail carries `oi_no` and `revision_state`; the Lines rows come from the
 *    worklist read (GET /order-inquiries?inquiry_id=...) and carry `oi_no`.
 * Harness copied from `SparePartRequestRecord.handtest.sparePart.test.tsx`.
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
class IntersectionObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { IntersectionObserver: unknown }).IntersectionObserver =
  IntersectionObserverStub;
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}
Element.prototype.scrollIntoView = vi.fn();

const push = vi.fn();
vi.mock('next/navigation', () => ({
  usePathname: () => '/procurement-management/spare-part-requests/spr-1',
  useRouter: () => ({ push, replace: vi.fn(), back: vi.fn(), prefetch: vi.fn(), refresh: vi.fn() }),
  useSearchParams: () => new URLSearchParams(''),
  useParams: () => ({ id: 'spr-1' }),
}));
vi.mock('next-auth/react', () => ({
  useSession: () => ({ data: { user: { id: 'u-1', name: 'ZZT Alice' } }, status: 'authenticated' }),
  SessionProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));
vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => true,
  useHasAnyPermission: () => true,
  usePermissions: () => ({ permissionSet: new Set(), permissions: [], isLoading: false, isError: false }),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));
vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: vi.fn(),
  cancelPendingAction: vi.fn(),
  getCurrentPendingAction: vi.fn().mockResolvedValue({ pending: null, last_outcome: null }),
}));
vi.mock('@/components/common/deferredToast', () => ({
  deferredToast: () => 'pending-action-1',
  dismissDeferredToast: vi.fn(),
}));

const SPR = '/api/v1/project-sales/spare-part-requests';

function detail(over: Record<string, unknown> = {}) {
  return {
    id: 'spr-1',
    inquiry_no: 'OI-2611-0009',
    inquiry_type: 'spare_part_request',
    state: 'pending_approval',
    currency: 'MYR',
    needed_by: '2026-12-15',
    default_location: 'BRW',
    reason: 'Spare parts for the service van',
    requested_by: 'u-1',
    requested_by_name: 'ZZT Alice',
    submitted_at: '2026-11-13T02:00:00',
    approved_at: null,
    approved_by: null,
    approved_by_name: null,
    reject_reason: null,
    can_decide: false,
    can_edit: true,
    can_revise: false,
    total: '50',
    lines: [
      {
        id: 'row-1',
        product_id: 'prod-1',
        item_code: 'SP-SEAL-40',
        product_name: 'Pump seal',
        description: 'Pump seal, left side',
        stock_location: 'BRW',
        qty: '2',
        unit_price: '25',
        total: '50',
        requested_qty: '2',
        requested_unit_price: '25',
        state: 'draft',
        ack_state: 'awaiting',
        photo_changes: { added: 0, removed: 0 },
      },
    ],
    ...over,
  };
}

const WORKLIST = '/api/v1/project-sales/order-inquiries';

function worklistRow(over: Record<string, unknown> = {}) {
  return {
    id: 'row-1',
    order_inquiry_id: 'spr-1',
    inquiry_no: 'OR-2611-0003',
    oi_no: 'OI-2611-0009',
    inquiry_type: 'spare_part_request',
    verb: 'REPLENISH',
    state: 'raised',
    ack_state: 'awaiting',
    item_code: 'ZZX-SEAL-40',
    product_id: 'prod-1',
    stock_location: 'BRW',
    qty: '2',
    unit_price: '25.0000',
    line_total: '50.0000',
    submitted_qty: '2',
    submitted_unit_price: '25.0000',
    photo_changes: { added: 0, removed: 0 },
    linked_qty: '0',
    bundled_qty: '0',
    ...over,
  };
}

let current = detail();
let rows = [worklistRow()];
const calls: string[] = [];
const ok = (b: unknown, status = 200) =>
  new Response(JSON.stringify(b), { status, headers: { 'content-type': 'application/json' } });
const apiFetch = vi.fn(async (url: string) => {
  calls.push(url);
  const path = url.split('?')[0];
  if (path === `${SPR}/spr-1`) return ok(current);
  if (path === WORKLIST) return ok({ data: rows, pagination: { total: rows.length, page: 1, limit: 1000 } });
  if (path.endsWith('/history')) return ok({ events: [] });
  if (path.endsWith('/attachments/lookup')) return ok({});
  if (path.endsWith('/spr-1')) return ok(current);
  return ok({ data: [], pagination: { total: 0, page: 1, limit: 25 } });
});
vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  apiFetch: (...a: [string, RequestInit?]) => apiFetch(a[0]),
}));

import * as RecordModule from './SparePartRequestRecord';

const SparePartRequestRecord = ((RecordModule as Record<string, unknown>).SparePartRequestRecord ??
  (RecordModule as Record<string, unknown>).default) as React.ComponentType<{ id: string }>;

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SparePartRequestRecord id="spr-1" />
    </QueryClientProvider>,
  );
}

const RAISED = {
  inquiry_no: 'OR-2611-0003',
  oi_no: 'OI-2611-0009',
  state: 'raised',
  can_edit: false,
  approved_at: '2026-11-13T05:00:00',
  revision_state: null,
};

beforeEach(() => {
  cleanup();
  calls.length = 0;
  vi.clearAllMocks();
  current = detail(RAISED);
  rows = [worklistRow()];
});

describe('U3.4: the OR page title stays the OR- number', () => {
  it('titled OR-2611-0003, never by its OI number', async () => {
    mount();
    const title = await screen.findByTestId('record-header-title-row');
    await waitFor(() => expect(title).toHaveTextContent('OR-2611-0003'));
    expect(title).not.toHaveTextContent('OI-2611-0009');
  });
});

describe('U3.2: the OR page Lines tab links each line to its OI row', () => {
  it('an "OI" column links OI-2611-0009 to the OI page at the row', async () => {
    mount();
    await screen.findByText('ZZX-SEAL-40', {}, { timeout: 5000 });
    const headers = screen.getAllByRole('columnheader').map((c) => (c.textContent ?? '').trim());
    expect(headers).toContain('OI');
    expect(headers).not.toContain('Order request');
    const link = screen.getByRole('link', { name: 'OI-2611-0009' });
    expect(link).toHaveAttribute('href', '/project-sales/order-inquiries/spr-1?row=row-1');
  });
});

describe('U3.3b: the OR page Lines start with PO hidden', () => {
  it('no PO column by default, so the OI column fits the card', async () => {
    mount();
    await screen.findByText('ZZX-SEAL-40', {}, { timeout: 5000 });
    const headers = screen.getAllByRole('columnheader').map((c) => (c.textContent ?? '').trim());
    expect(headers).toContain('OI');
    expect(headers).not.toContain('PO');
  });
});

describe('U4.6: the OR status pill reads the open revision', () => {
  it.each([
    ['draft', 'Draft'],
    ['pending_approval', 'Pending approval'],
    ['rejected', 'Rejected'],
  ])('revision_state %s reads %s, not Approved', async (revision, label) => {
    current = detail({ ...RAISED, revision_state: revision });
    mount();
    const title = await screen.findByTestId('record-header-title-row');
    await waitFor(() => expect(title).toHaveTextContent(label));
    expect(title).not.toHaveTextContent('Approved');
  });

  it('no revision open: Approved', async () => {
    mount();
    const title = await screen.findByTestId('record-header-title-row');
    await waitFor(() => expect(title).toHaveTextContent('Approved'));
  });
});
