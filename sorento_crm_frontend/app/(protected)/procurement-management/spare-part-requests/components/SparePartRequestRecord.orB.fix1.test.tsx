/**
 * SPARE-PART-OR-B fix round 1, red-first. Item 9b: the OR page Approve popup during a
 * revision compares the REVISED qty against the APPROVED qty (not the first submission):
 * the total is revised qty x unit price, and "Your changes" reads "<code> qty 10 to 12" for
 * an approved 10 revised to 12, never "8 to 12" off the original submitted 8.
 * Harness copied from `SparePartRequestRecord.orB.test.tsx`.
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { formatMoneyExact } from '@/app/(protected)/project-sales/_shared/lib/money';
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


describe('item 9b: the Approve popup during a revision', () => {
  beforeEach(() => {
    current = detail({
      ...RAISED,
      revision_state: 'pending_approval',
      can_decide: true,
      lines: [
        {
          id: 'row-1', product_id: 'prod-1', item_code: 'ZZX-SEAL-40', product_name: 'Seal',
          description: null, stock_location: 'BRW', qty: '12', unit_price: '25', total: '300',
          requested_qty: '8', requested_unit_price: '25', state: 'raised', ack_state: 'awaiting',
          photo_changes: { added: 0, removed: 0 },
        },
      ],
      total: '300',
    });
    rows = [
      worklistRow({ qty: '10', submitted_qty: '8', unit_price: '25.0000', submitted_unit_price: '25.0000', line_total: '250.0000' }),
    ];
  });

  async function openApprove() {
    mount();
    const button = await screen.findByRole('button', { name: /^approve$/i }, { timeout: 5000 });
    await screen.findByText('ZZX-SEAL-40', {}, { timeout: 5000 });
    fireEvent.click(button);
    return screen.findByRole('dialog');
  }

  it('the total is the revised qty x unit price', async () => {
    const dialog = await openApprove();
    await waitFor(() => expect(dialog).toHaveTextContent(formatMoneyExact('300', 'MYR')));
    expect(dialog).not.toHaveTextContent(formatMoneyExact('250', 'MYR'));
  });

  it('"Your changes" compares against the approved qty', async () => {
    const dialog = await openApprove();
    expect(within(dialog).getByText(/qty 10 to 12/)).toBeInTheDocument();
    expect(dialog).not.toHaveTextContent(/qty 8 to/);
  });
});
