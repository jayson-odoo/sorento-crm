/**
 * SPARE-PART-ORDER-REQUEST review round 2 (review S2), red-first (Phase 2).
 *
 * R5 a stale decision is refused: the approver's Approve and Reject send the `submitted_at`
 *    of the request they rendered (the detail returns it), so a decision on a request the
 *    requester has since edited (approval restarted) answers 409 instead of approving what
 *    the approver never saw. The 409's plain message is shown (GUARD: the hooks already toast
 *    the server's message). Backend half: tests/test_spare_part_request_review2.py R5.
 *
 * Asserted at the HTTP seam (`apiFetch`), so it holds however the coder threads the value.
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => '/procurement-management/spare-part-requests/oi-1',
  useSearchParams: () => new URLSearchParams(''),
}));
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() }));
vi.mock('@/lib/toast', () => ({ toast }));
vi.mock('@/components/common/deferredToast', () => ({
  deferredToast: () => 'pending-action-1',
  dismissDeferredToast: vi.fn(),
}));
vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: vi.fn(),
  cancelPendingAction: vi.fn(),
  getCurrentPendingAction: vi.fn().mockResolvedValue({ pending: null, last_outcome: null }),
}));

const SUBMITTED_AT = '2026-11-13T02:00:00.123456';
const BASE = '/api/v1/project-sales/spare-part-requests/oi-1';

type Call = { url: string; method: string; body: Record<string, unknown> | null };
const calls: Call[] = [];
let answer: { status: number; body: unknown } = { status: 200, body: {} };
const apiFetch = vi.fn(async (url: string, init?: RequestInit) => {
  let body: Record<string, unknown> | null = null;
  if (typeof init?.body === 'string') {
    try {
      body = JSON.parse(init.body);
    } catch {
      body = null;
    }
  }
  calls.push({ url, method: (init?.method ?? 'GET').toUpperCase(), body });
  const decision = url === `${BASE}/approve` || url === `${BASE}/reject`;
  const { status, body: out } = decision ? answer : { status: 200, body: {} };
  return new Response(JSON.stringify(out), { status, headers: { 'content-type': 'application/json' } });
});
vi.mock('@/lib/api', () => ({ apiFetch: (...a: [string, RequestInit?]) => apiFetch(...a) }));

import { SparePartRequestActions } from './SparePartRequestActions';
import type {
  OrderInquiryHeaderDetail,
  OrderInquiryWorklistRow,
} from '../../../_shared/types/orderInquiry.types';

function header(over: Record<string, unknown> = {}): OrderInquiryHeaderDetail {
  return {
    id: 'oi-1',
    inquiry_no: 'OI-2611-0007',
    inquiry_type: 'spare_part_request',
    state: 'pending_approval',
    currency: 'MYR',
    submitted_at: SUBMITTED_AT,
    can_edit: false,
    can_decide: true,
    can_revise: false,
    raise_history: [],
    ...over,
  } as unknown as OrderInquiryHeaderDetail;
}

const ROW = {
  id: 'row-1',
  verb: 'REPLENISH',
  state: 'draft',
  item_code: 'SP-SEAL-40',
  qty: '10',
  unit_price: '25',
  line_total: '250',
  submitted_qty: '10',
  submitted_unit_price: '25',
  photo_changes: { added: 0, removed: 0 },
} as unknown as OrderInquiryWorklistRow;

function mount(h = header()) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <SparePartRequestActions header={h} rows={[ROW]} />
    </QueryClientProvider>,
  );
}

const decisionCall = (verb: 'approve' | 'reject') =>
  calls.find((c) => c.url === `${BASE}/${verb}` && c.method === 'POST');

async function approveFromPopup() {
  fireEvent.click(screen.getByRole('button', { name: 'Approve' }));
  const dialog = await screen.findByRole('dialog');
  fireEvent.click(within(dialog).getByRole('button', { name: 'Approve' }));
}

async function rejectFromPopup(reason = 'Too dear') {
  fireEvent.click(screen.getByRole('button', { name: 'Reject' }));
  const dialog = await screen.findByRole('dialog');
  fireEvent.change(within(dialog).getByLabelText(/reason/i), { target: { value: reason } });
  fireEvent.click(within(dialog).getByRole('button', { name: 'Reject' }));
}

beforeEach(() => {
  cleanup();
  calls.length = 0;
  vi.clearAllMocks();
  answer = { status: 200, body: { id: 'oi-1', state: 'raised' } };
});

describe('R5 (S2): Approve and Reject send the submitted_at they rendered', () => {
  it('Approve posts the rendered submitted_at', async () => {
    mount();
    await approveFromPopup();
    await waitFor(() => expect(decisionCall('approve')).toBeTruthy());
    expect(decisionCall('approve')?.body?.submitted_at, 'approve body submitted_at').toBe(SUBMITTED_AT);
  });

  it('Reject posts the rendered submitted_at with the reason', async () => {
    answer = { status: 200, body: { id: 'oi-1', state: 'rejected' } };
    mount();
    await rejectFromPopup('Too dear');
    await waitFor(() => expect(decisionCall('reject')).toBeTruthy());
    const body = decisionCall('reject')?.body;
    expect(body?.reason).toBe('Too dear');
    expect(body?.submitted_at, 'reject body submitted_at').toBe(SUBMITTED_AT);
  });

  it("a 409 for a request changed since it was opened shows the server's plain message (guard)", async () => {
    const message = 'This request was changed after you opened it. Open it again to see the changes.';
    answer = { status: 409, body: { message, detail: null, code: 'SPARE_PART_REQUEST_STALE' } };
    mount();
    await approveFromPopup();
    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(toast.error).toHaveBeenCalledWith(message);
    expect(toast.success).not.toHaveBeenCalled();
  });
});
