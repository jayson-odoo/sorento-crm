/**
 * SCM M8 — useReorderPlan (slice C, Phase 2, test-first). The shared plan state:
 * adapts the run's buy recs onto grid rows, SEEDS pins/rejects/edits from the
 * decision overlay, runs the pin-aware budget split LIVE, and lands every decision
 * on the server.
 *   M8-C2 clearable budget + pin-aware split · M8-C3 pins win / free goes negative
 *   M8-C5 inline edit → POST /adjust with supplier CODE · M8-C6 accept/reject
 *   seed pins/rejects from decision overlay (accepted/adjusted → pin, dismissed → reject)
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));

const toastError = vi.fn();
const toastSuccess = vi.fn();
vi.mock('sonner', () => ({
  toast: { error: (...a: unknown[]) => toastError(...a), success: (...a: unknown[]) => toastSuccess(...a) },
}));

import { useReorderPlan } from './useReorderPlan';
import type { ReorderRecommendation, SupplierChoice } from '../types/reorder.types';
import type { RecDecision } from '../types/decisions.types';

function ok(body: unknown) {
  return { ok: true, status: 200, headers: { get: () => 'application/json' }, json: async () => body } as unknown as Response;
}
function fail(detail: string) {
  return {
    ok: false, status: 400, headers: { get: () => 'application/json' },
    json: async () => ({ detail }), text: async () => JSON.stringify({ detail }),
  } as unknown as Response;
}

const beta: SupplierChoice = {
  supplier_code: 'SUP-BETA', supplier_name: 'Beta Supplies', unit_cost: 80,
  lead_time_days: 21, composite_score: 80, is_primary: false,
};

/** Buy rec — qty 10 × unit_cost 100 = 1000 cash each; beta alt at 80. */
function rec(id: string, rank: number): ReorderRecommendation {
  return {
    id, type: 'buy', sku: `SKU-${id}`, product_name: `Product ${id}`,
    abc_class: 'A', xyz_class: 'X', warehouse_code: 'WH-KL', warehouse_name: 'Kuala Lumpur DC',
    product_id: `prod-${id}`, warehouse_id: 'wh-1', is_network: false, allocation: null,
    order_qty: 10, recommended_qty: 10, reorder_point: 5, min_qty: null, max_qty: null,
    order_up_to: 20, net_position: 3, days_of_cover: 6, reason: 'reorder_point',
    reason_label: 'net ≤ ROP', confidence: 'high', sample_size: 40,
    supplier: { supplier_code: 'SUP-ACME', supplier_name: 'Acme', unit_cost: 100, lead_time_days: 14, composite_score: 88, is_primary: true },
    alternatives: [beta], is_exception: false, disposition_action: null, transfer_flag: null,
    forecast_daily_demand: 1, lead_time_days: 14, lead_time_source: 'measured', safety_stock: 2,
    safety_stock_method: 'fixed_days', safety_stock_fallback: null, service_level: 0.95, safety_days: 7,
    review_days: 30, moq: 1, order_multiple: 1, policy_type: 'reorder_point', supplier_selection: 'primary',
    unit_cost: 100, cash_impact: 1000, rank, rank_score: 1 - rank / 100, funding_status: null,
    days_to_stockout: rank, rank_factors: [],
  };
}

/** Route apiFetch by url + method. `decisions` seeds the overlay; adjust bodies captured. */
function routeApi(recs: ReorderRecommendation[], decisions: RecDecision[] = []) {
  apiFetch.mockImplementation((url: string, init?: RequestInit) => {
    const method = init?.method ?? 'GET';
    if (method === 'POST' && url.includes('/accept')) return Promise.resolve(ok({ draft_po_number: null, draft_po_id: null, supplier_name: 'Acme' }));
    if (method === 'POST' && url.includes('/adjust')) return Promise.resolve(ok({ draft_po_number: null, draft_po_id: null, supplier_name: 'Beta Supplies' }));
    if (method === 'POST' && url.includes('/reject')) return Promise.resolve(ok({}));
    if (method === 'POST' && url.includes('/confirm-decisions')) return Promise.resolve(ok({ confirmed_count: 1, po_count: 1 }));
    if (method === 'PUT' && url.includes('/budget')) return Promise.resolve(ok({ run_id: 'run-1', budget: 0, funded_count: 0, deferred_count: 0, needs_cost_count: 0, funded_cash: 0, deferred_cash: 0 }));
    if (url.includes('/decisions')) return Promise.resolve(ok({ data: decisions }));
    if (url.includes('/recommendations')) return Promise.resolve(ok({ data: recs, pagination: { page: 1, limit: 1000, total: recs.length, total_pages: 1 } }));
    return Promise.resolve(ok({}));
  });
}

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return React.createElement(QueryClientProvider, { client }, children);
}

/** Body of the last apiFetch call whose url matches `frag`. */
function lastBody(frag: string): Record<string, unknown> {
  const call = [...apiFetch.mock.calls].reverse().find((c) => String(c[0]).includes(frag));
  return JSON.parse(String((call?.[1] as RequestInit)?.body ?? '{}'));
}

beforeEach(() => {
  apiFetch.mockReset();
  toastError.mockReset();
  toastSuccess.mockReset();
});

describe('useReorderPlan — adapter + rows', () => {
  it('loads the run’s buy recs and adapts them onto M8 grid rows', async () => {
    routeApi([rec('a', 1), rec('b', 2)]);
    const { result } = renderHook(() => useReorderPlan('run-1', true), { wrapper });
    await waitFor(() => expect(result.current.rows).toHaveLength(2));
    expect(result.current.rows[0].sku).toBe('SKU-a');
    expect(result.current.rows[0].warehouse).toBe('Kuala Lumpur DC');
    expect(result.current.rows[0].original_order_qty).toBe(10);
  });

  it('does not load when disabled (non-buy view)', () => {
    routeApi([rec('a', 1)]);
    renderHook(() => useReorderPlan('run-1', false), { wrapper });
    expect(apiFetch).not.toHaveBeenCalled();
  });
});

describe('useReorderPlan — seed pins/rejects/edits from the decision overlay', () => {
  it('accepted → pin, dismissed → reject, adjusted → pin + edited row (override qty applied)', async () => {
    const decisions: RecDecision[] = [
      { recommendation_id: 'a', status: 'accepted', override_qty: null, override_supplier_code: null, override_supplier_name: null, reason_text: null, draft_po_number: null, draft_po_id: null },
      { recommendation_id: 'b', status: 'dismissed', override_qty: null, override_supplier_code: null, override_supplier_name: null, reason_text: 'discontinued', draft_po_number: null, draft_po_id: null },
      { recommendation_id: 'c', status: 'adjusted', override_qty: 25, override_supplier_code: 'SUP-BETA', override_supplier_name: 'Beta Supplies', reason_text: 'seasonal', draft_po_number: null, draft_po_id: null },
    ];
    routeApi([rec('a', 1), rec('b', 2), rec('c', 3)], decisions);
    const { result } = renderHook(() => useReorderPlan('run-1', true), { wrapper });
    await waitFor(() => expect(result.current.pins.has('a')).toBe(true));

    expect(result.current.decisions['a']).toBe('accepted');
    expect(result.current.rejects.has('b')).toBe(true);
    expect(result.current.decisions['b']).toBe('rejected');
    expect(result.current.pins.has('c')).toBe(true);
    expect(result.current.editedIds.has('c')).toBe(true);
    // the adjusted override qty + supplier swap is applied on the grid row
    const rowC = result.current.rows.find((r) => r.id === 'c')!;
    expect(rowC.order_qty).toBe(25);
    expect(rowC.supplier.code).toBe('SUP-BETA');
    expect(rowC.unit_cost).toBe(80);
  });

  it('exposes poByRow for lines already materialised into a draft PO (M8-F8/M8-F9)', async () => {
    const decisions: RecDecision[] = [
      // accepted + confirmed → carries a draft PO number/id
      { recommendation_id: 'a', status: 'accepted', override_qty: null, override_supplier_code: null, override_supplier_name: null, reason_text: null, draft_po_number: 'PO-2026-0007', draft_po_id: 'po-abc' },
      // accepted but not yet confirmed → no PO
      { recommendation_id: 'b', status: 'accepted', override_qty: null, override_supplier_code: null, override_supplier_name: null, reason_text: null, draft_po_number: null, draft_po_id: null },
    ];
    routeApi([rec('a', 1), rec('b', 2)], decisions);
    const { result } = renderHook(() => useReorderPlan('run-1', true), { wrapper });
    await waitFor(() => expect(result.current.poByRow['a']).toBeTruthy());
    expect(result.current.poByRow['a']).toEqual({ po_number: 'PO-2026-0007', po_id: 'po-abc' });
    // a line without a PO is absent from the map (still pending confirmation)
    expect(result.current.poByRow['b']).toBeUndefined();
  });
});

describe('useReorderPlan — pin-aware budget split (M8-C2 / M8-C3)', () => {
  it('clearing the budget to 0 defers every un-pinned costed row (committed 0)', async () => {
    routeApi([rec('a', 1), rec('b', 2), rec('c', 3)]);
    const { result } = renderHook(() => useReorderPlan('run-1', true), { wrapper });
    await waitFor(() => expect(result.current.rows).toHaveLength(3));
    act(() => result.current.setBudget(0));
    await waitFor(() => expect(result.current.funding.within).toHaveLength(0));
    expect(result.current.funding.over).toHaveLength(3);
    expect(result.current.funding.committed).toBe(0);
  });

  it('a pinned line force-funds and stays within on a budget cut; free goes negative (M8-C3)', async () => {
    routeApi([rec('a', 1), rec('b', 2), rec('c', 3)]);
    const { result } = renderHook(() => useReorderPlan('run-1', true), { wrapper });
    await waitFor(() => expect(result.current.rows).toHaveLength(3));

    // Pin the lowest-ranked row, then cut the budget below its cost (1000).
    act(() => result.current.fund(result.current.rows.find((r) => r.id === 'c')!));
    act(() => result.current.setBudget(500));
    await waitFor(() =>
      expect(result.current.funding.within.map((r) => r.id)).toContain('c'),
    );
    // pin consumed budget first → overspend, free negative, un-pinned all over
    expect(result.current.funding.committed).toBe(1000);
    expect(result.current.funding.free).toBe(-500);
    expect(result.current.funding.over.map((r) => r.id).sort()).toEqual(['a', 'b']);
  });
});

describe('useReorderPlan — sticky sections (M8-F12)', () => {
  it('rejecting a within-budget line does NOT reflow the table — no row moves sections, cash drops from committed', async () => {
    routeApi([rec('a', 1), rec('b', 2), rec('c', 3)]);
    const { result } = renderHook(() => useReorderPlan('run-1', true), { wrapper });
    await waitFor(() => expect(result.current.rows).toHaveLength(3));
    // Raise the budget so all three fund (a budget change is the only thing that
    // re-sections) — baseline: 3 within, 0 over, RM3000 committed.
    act(() => result.current.setBudget(5000));
    await waitFor(() => expect(result.current.funding.within).toHaveLength(3));
    const withinBefore = result.current.funding.within.map((r) => r.id);
    const committedBefore = result.current.funding.committed;
    expect(committedBefore).toBe(3000);

    // Reject one within-budget line.
    await act(async () => {
      result.current.reject(result.current.funding.within[0], 'overstocked already');
    });
    await waitFor(() => expect(result.current.rejects.has('a')).toBe(true));

    // Section membership is byte-identical — the rejected row STAYS within (greyed in
    // the UI), and the freed budget does NOT auto-promote any over-budget row.
    expect(result.current.funding.within.map((r) => r.id)).toEqual(withinBefore);
    expect(result.current.funding.over).toHaveLength(0);
    // Only the committed/free totals move: the rejected line's RM1000 leaves committed.
    expect(result.current.funding.committed).toBe(committedBefore - 1000);
    expect(result.current.funding.free).toBe(5000 - (committedBefore - 1000));
  });

  it('accepting a within-budget line does NOT reflow sections (only budget changes re-split)', async () => {
    routeApi([rec('a', 1), rec('b', 2), rec('c', 3)]);
    const { result } = renderHook(() => useReorderPlan('run-1', true), { wrapper });
    await waitFor(() => expect(result.current.rows).toHaveLength(3));
    act(() => result.current.setBudget(1500)); // funds a + b (2×1000 ≤ 1500? no: 1000 then 1000>500) → a within, b/c over
    await waitFor(() => expect(result.current.funding.within.map((r) => r.id)).toEqual(['a']));
    const overBefore = result.current.funding.over.map((r) => r.id);

    // Accept the within row — it pins but must not move any over-budget row up.
    await act(async () => {
      result.current.fund(result.current.funding.within[0]);
    });
    await waitFor(() => expect(result.current.pins.has('a')).toBe(true));
    expect(result.current.funding.within.map((r) => r.id)).toEqual(['a']);
    expect(result.current.funding.over.map((r) => r.id)).toEqual(overBefore);
  });
});

describe('useReorderPlan — server decisions', () => {
  it('fund → POST /accept and pins the row (M8-C6)', async () => {
    routeApi([rec('a', 1)]);
    const { result } = renderHook(() => useReorderPlan('run-1', true), { wrapper });
    await waitFor(() => expect(result.current.rows).toHaveLength(1));
    await act(async () => {
      result.current.fund(result.current.rows[0]);
    });
    await waitFor(() => expect(result.current.pins.has('a')).toBe(true));
    expect(apiFetch).toHaveBeenCalledWith('/api/v1/scm/recommendations/a/accept', expect.objectContaining({ method: 'POST' }));
  });

  it('reject → POST /reject with the reason and marks the row rejected (M8-C6)', async () => {
    routeApi([rec('a', 1)]);
    const { result } = renderHook(() => useReorderPlan('run-1', true), { wrapper });
    await waitFor(() => expect(result.current.rows).toHaveLength(1));
    await act(async () => {
      result.current.reject(result.current.rows[0], 'overstocked already');
    });
    await waitFor(() => expect(result.current.rejects.has('a')).toBe(true));
    expect(lastBody('/reject')).toEqual({ reason_text: 'overstocked already' });
  });

  it('editRow → POST /adjust sends the supplier CODE (override_supplier_id) + qty, pins + edits (M8-C5)', async () => {
    routeApi([rec('a', 1)]);
    const { result } = renderHook(() => useReorderPlan('run-1', true), { wrapper });
    await waitFor(() => expect(result.current.rows).toHaveLength(1));
    await act(async () => {
      result.current.editRow(result.current.rows[0], { order_qty: 20, supplier_code: 'SUP-BETA' }, 'switch to cheaper');
    });
    await waitFor(() => expect(result.current.editedIds.has('a')).toBe(true));
    // decisionService maps override_supplier_code → override_supplier_id (the CODE) on the wire
    expect(lastBody('/adjust')).toEqual({
      override_qty: 20,
      override_supplier_id: 'SUP-BETA',
      reason_text: 'switch to cheaper',
    });
    // the row reflects the swap live (qty + swapped unit cost) and is pinned
    const row = result.current.rows[0];
    expect(row.order_qty).toBe(20);
    expect(row.unit_cost).toBe(80);
    expect(result.current.pins.has('a')).toBe(true);
  });

  it('applyProposalLine → POST /adjust with the market-bumped qty (M8-E5)', async () => {
    routeApi([rec('a', 1)]);
    const { result } = renderHook(() => useReorderPlan('run-1', true), { wrapper });
    await waitFor(() => expect(result.current.rows).toHaveLength(1));
    await act(async () => {
      result.current.applyProposalLine({ row_id: 'a', sku: 'SKU-a', product_name: 'Product a', old_qty: 10, new_qty: 40, unit_cost: 100, reason: 'market surge +8%' });
    });
    await waitFor(() => expect(result.current.editedIds.has('a')).toBe(true));
    expect(lastBody('/adjust')).toMatchObject({ override_qty: 40, reason_text: 'market surge +8%' });
    expect(result.current.rows[0].order_qty).toBe(40);
  });

  it('applyActions → routes accept/reject/adjust lines through the existing decision endpoints (M8-F16)', async () => {
    routeApi([rec('a', 1), rec('b', 2), rec('c', 3)]);
    const { result } = renderHook(() => useReorderPlan('run-1', true), { wrapper });
    await waitFor(() => expect(result.current.rows).toHaveLength(3));
    await act(async () => {
      result.current.applyActions([
        { rec_id: 'a', sku: 'SKU-a', product_name: 'Product a', action: 'accept', current_qty: 10, new_qty: null, reason: 'wanted' },
        { rec_id: 'b', sku: 'SKU-b', product_name: 'Product b', action: 'reject', current_qty: 10, new_qty: null, reason: 'not wanted' },
        { rec_id: 'c', sku: 'SKU-c', product_name: 'Product c', action: 'adjust', current_qty: 10, new_qty: 30, reason: 'bump to MoQ' },
      ]);
    });
    await waitFor(() => expect(result.current.pins.has('a')).toBe(true));
    // accept → pin, reject → reject flag, adjust → edited row with the new qty
    expect(result.current.rejects.has('b')).toBe(true);
    await waitFor(() => expect(result.current.editedIds.has('c')).toBe(true));
    expect(lastBody('/reject')).toEqual({ reason_text: 'not wanted' });
    expect(lastBody('/adjust')).toMatchObject({ override_qty: 30, reason_text: 'bump to MoQ' });
    // a summary success toast confirms the Apply
    expect(toastSuccess).toHaveBeenCalledWith(expect.stringContaining('Applied 3 plan actions'));
  });

  it('applyActions → counts a line whose rec left the plan as failed, applies the rest', async () => {
    routeApi([rec('a', 1)]);
    const { result } = renderHook(() => useReorderPlan('run-1', true), { wrapper });
    await waitFor(() => expect(result.current.rows).toHaveLength(1));
    let outcome: { applied: number; failed: number } | undefined;
    await act(async () => {
      outcome = result.current.applyActions([
        { rec_id: 'a', sku: 'SKU-a', product_name: 'Product a', action: 'accept', current_qty: 10, new_qty: null, reason: 'ok' },
        { rec_id: 'gone', sku: 'SKU-gone', product_name: 'Gone', action: 'reject', current_qty: 10, new_qty: null, reason: 'x' },
      ]);
    });
    expect(outcome).toEqual({ applied: 1, failed: 1 });
    expect(result.current.pins.has('a')).toBe(true);
  });

  it('surfaces a failed accept via toast (optimistic pin already applied)', async () => {
    routeApi([rec('a', 1)]);
    apiFetch.mockImplementation((url: string, init?: RequestInit) => {
      const method = init?.method ?? 'GET';
      if (method === 'POST' && url.includes('/accept')) return Promise.resolve(fail('Already decided'));
      if (url.includes('/decisions')) return Promise.resolve(ok({ data: [] }));
      if (url.includes('/recommendations')) return Promise.resolve(ok({ data: [rec('a', 1)], pagination: { page: 1, limit: 1000, total: 1, total_pages: 1 } }));
      return Promise.resolve(ok({}));
    });
    const { result } = renderHook(() => useReorderPlan('run-1', true), { wrapper });
    await waitFor(() => expect(result.current.rows).toHaveLength(1));
    await act(async () => {
      result.current.fund(result.current.rows[0]);
    });
    await waitFor(() => expect(toastError).toHaveBeenCalled());
  });
});
