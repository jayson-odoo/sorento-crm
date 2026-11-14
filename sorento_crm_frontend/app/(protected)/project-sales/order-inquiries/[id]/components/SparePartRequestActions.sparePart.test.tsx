/**
 * SPARE-PART-ORDER-REQUEST fix round 1, red-first (Phase 2).
 *
 * G1 Delete draft (mock v5; CRUD standard D7): the request's header actions offer Delete on
 * a Draft or Rejected request the viewer may edit. Delete parks the server-deferred
 * `spare_part_request.delete` pending action (the countdown, `useDeferredAction`, as
 * `NewProductApplicationDetail.tsx`'s "Delete draft"); it never asks `confirm()` and opens no
 * dialog. Never offered once pending, raised, or to the approver. Delete is not the filled
 * main button (Submit stays it).
 *
 * G2 The Approve popup lists the approver's photo changes beside qty and unit price changes.
 * NAMED ASSUMPTION: each worklist row carries `photo_changes: { added, removed }` (the field the
 * backend fix-round test requires, `tests/test_spare_part_request_fix1.py`), and
 * `approverChanges(rows)` turns it into "<item> 1 photo added" / "<item> 2 photos removed".
 *
 * Asserted at the service seam (`pendingActionService`, `apiFetch`), so it holds however the
 * coder wires the hook.
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
  usePathname: () => '/project-sales/order-inquiries/oi-1',
  useSearchParams: () => new URLSearchParams(''),
}));
vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));
vi.mock('@/components/common/deferredToast', () => ({
  deferredToast: () => 'pending-action-1',
  dismissDeferredToast: vi.fn(),
}));

const createPendingAction = vi.fn().mockResolvedValue({
  id: 'pa-1',
  action_key: 'spare_part_request.delete',
  entity_type: 'spare_part_request',
  entity_id: 'oi-1',
  commit_at: '2026-11-13T10:00:10',
  window_seconds: 10,
});
vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: (...args: unknown[]) => createPendingAction(...args),
  cancelPendingAction: vi.fn(),
  getCurrentPendingAction: vi.fn().mockResolvedValue({ pending: null, last_outcome: null }),
}));

const apiFetch = vi.fn(
  async () =>
    new Response(JSON.stringify({}), { status: 200, headers: { 'content-type': 'application/json' } }),
);
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...(a as [])) }));

import { SparePartRequestActions, approverChanges } from './SparePartRequestActions';
import type {
  OrderInquiryHeaderDetail,
  OrderInquiryWorklistRow,
} from '../../../_shared/types/orderInquiry.types';

function header(over: Record<string, unknown>): OrderInquiryHeaderDetail {
  return {
    id: 'oi-1',
    inquiry_no: 'OI-2611-0007',
    inquiry_type: 'spare_part_request',
    state: 'draft',
    currency: 'MYR',
    can_edit: true,
    can_decide: false,
    can_revise: false,
    raise_history: [],
    ...over,
  } as unknown as OrderInquiryHeaderDetail;
}

function row(over: Record<string, unknown>): OrderInquiryWorklistRow {
  return {
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
    ...over,
  } as unknown as OrderInquiryWorklistRow;
}

function mount(h: OrderInquiryHeaderDetail, rows: OrderInquiryWorklistRow[] = [row({})]) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SparePartRequestActions header={h} rows={rows} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('G1 / D7: Delete draft is a countdown, never a confirm', () => {
  it('a draft offers Delete; pressing it parks spare_part_request.delete with no confirm and no dialog', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    mount(header({ state: 'draft' }));
    fireEvent.click(screen.getByRole('button', { name: /^Delete/ }));

    await waitFor(() =>
      expect(createPendingAction).toHaveBeenCalledWith(
        expect.objectContaining({
          actionKey: 'spare_part_request.delete',
          entityType: 'spare_part_request',
          entityId: 'oi-1',
        }),
      ),
    );
    expect(confirmSpy).not.toHaveBeenCalled();
    expect(screen.queryByRole('alertdialog')).toBeNull();
    expect(screen.queryByRole('dialog')).toBeNull();
    confirmSpy.mockRestore();
  });

  it('a rejected request the requester may edit offers Delete', () => {
    mount(header({ state: 'rejected' }));
    expect(screen.getByRole('button', { name: /^Delete/ })).toBeInTheDocument();
  });

  it('Delete is not the filled main button; Submit is', () => {
    mount(header({ state: 'draft' }));
    expect(screen.getByRole('button', { name: /^Delete/ }).className).not.toMatch(/\bbg-primary\b/);
    expect(screen.getByRole('button', { name: 'Submit' }).className).toMatch(/\bbg-primary\b/);
  });

  it('never offered on a pending request, to the approver, or once raised', () => {
    mount(header({ state: 'pending_approval', can_edit: false, can_decide: true }));
    expect(screen.queryByRole('button', { name: /^Delete/ })).toBeNull();
    cleanup();
    mount(header({ state: 'raised', can_edit: false, can_revise: true }));
    expect(screen.queryByRole('button', { name: /^Delete/ })).toBeNull();
  });
});

describe('G2: the Approve popup lists photo changes', () => {
  it('approverChanges names photos added and removed per line', () => {
    const changes = approverChanges([
      row({ id: 'r1', item_code: 'SP-SEAL-40', photo_changes: { added: 0, removed: 2 } }),
      row({ id: 'r2', item_code: 'SP-HINGE', photo_changes: { added: 1, removed: 0 } }),
    ]);
    expect(changes.some((c) => /SP-HINGE\b.*\b1 photo added\b/.test(c))).toBe(true);
    expect(changes.some((c) => /SP-SEAL-40\b.*\b2 photos removed\b/.test(c))).toBe(true);
  });

  it('keeps listing qty and unit price changes beside them', () => {
    const changes = approverChanges([
      row({ qty: '6', line_total: '150', photo_changes: { added: 1, removed: 0 } }),
    ]);
    expect(changes.some((c) => /qty 10 to 6/.test(c))).toBe(true);
    expect(changes.some((c) => /1 photo added/.test(c))).toBe(true);
  });

  it('a row with no photo change (or an older payload without the field) adds no photo line', () => {
    const changes = approverChanges([row({}), row({ id: 'r2', photo_changes: undefined })]);
    expect(changes.filter((c) => /photo/.test(c))).toEqual([]);
  });

  it('the popup shows the photo change', () => {
    mount(header({ state: 'pending_approval', can_edit: false, can_decide: true }), [
      row({ state: 'draft', item_code: 'SP-HINGE', photo_changes: { added: 1, removed: 0 } }),
    ]);
    fireEvent.click(screen.getByRole('button', { name: 'Approve' }));
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText(/1 photo added/)).toBeInTheDocument();
    expect(within(dialog).queryByText('No changes to the submitted lines.')).toBeNull();
  });
});
