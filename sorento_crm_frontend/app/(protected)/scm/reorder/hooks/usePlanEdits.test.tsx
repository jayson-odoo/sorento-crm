/**
 * usePlanEdits - the draft map and the two buttons that end it (plan 4.5, UAC D7, E1-E4).
 *
 * The map is keyed by ROW id (a product-grain row is several recommendations underneath),
 * and the fan-out to every member happens here, at save time - the same place
 * `usePlanLines.decide`/`.updateMoq` already fan writes out. Everything here is mocked at
 * the service boundary (`savePlanEdits`, `confirmDecisions`); the arithmetic itself
 * (`editedProductCount`, `hasRowEdit`, ...) has its own suite in `lib/planEdits.test.ts`.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReorderRecommendation } from '../types/reorder.types';
import { recToPlanLine, type PlanLine } from '../lib/planLine';
import { groupPlanLinesByChannel } from '../lib/planLineGrouping';
import type { PlanDecisionMap } from '../lib/planDecisions';

const savePlanEdits = vi.fn();
vi.mock('../services/planEditsService', () => ({
  savePlanEdits: (...a: unknown[]) => savePlanEdits(...a),
}));

const confirmDecisions = vi.fn();
vi.mock('../services/decisionService', () => ({
  confirmDecisions: (...a: unknown[]) => confirmDecisions(...a),
}));

import { usePlanEdits } from './usePlanEdits';

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return React.createElement(QueryClientProvider, { client }, children);
}

function rec(over: Partial<ReorderRecommendation> = {}): ReorderRecommendation {
  return {
    id: 'r1', type: 'buy', sku: 'SKU-1', product_name: 'Product one',
    abc_class: null, xyz_class: null, warehouse_code: 'BRW', warehouse_name: 'Butterworth',
    product_id: 'p1', warehouse_id: 'w1', is_network: false, allocation: null,
    order_qty: 23, recommended_qty: 23, reorder_point: 0, min_qty: null, max_qty: null,
    order_up_to: 0, net_position: -23, days_of_cover: null, reason: 'reorder_point',
    reason_label: '', confidence: 'low', sample_size: 0,
    supplier: { supplier_code: 'S1', supplier_name: 'Acme', unit_cost: 10,
                lead_time_days: 30, composite_score: 0, is_primary: true },
    alternatives: [], is_exception: false, disposition_action: null, transfer_flag: null,
    forecast_daily_demand: 0, lead_time_days: 30, lead_time_source: 'default',
    safety_stock: 0, safety_stock_method: null, safety_stock_fallback: null,
    service_level: null, safety_days: 0, review_days: 0,
    moq: null, master_moq: null, moq_is_override: false,
    order_multiple: null, policy_type: 'reorder_point', supplier_selection: 'primary',
    unit_cost: 10, cash_impact: 230, rank: 1, rank_score: 0, funding_status: null,
    days_to_stockout: null, rank_factors: [],
    on_hand: 1, incoming_spo: 0, outstanding_po: 0, outstanding_sales: 24,
    project_committed: 0, retail_committed: 24,
    segment: 'dealer',
    ...over,
  } as ReorderRecommendation;
}

const line = (over: Partial<ReorderRecommendation> = {}): PlanLine => recToPlanLine(rec(over));

beforeEach(() => {
  savePlanEdits.mockReset().mockResolvedValue({ saved_rows: 1, saved_products: 1 });
  confirmDecisions.mockReset().mockResolvedValue({ confirmed_count: 1, po_count: 1 });
});

describe('usePlanEdits - the draft map (D7)', () => {
  it('setRowEdit lands the patch under the row id, ready for planPillReading to read Unsaved', async () => {
    const l = line();
    const { result } = renderHook(() => usePlanEdits('run-1', [l], {}), { wrapper });

    act(() => result.current.setRowEdit(l, { moq: 100 }));

    await waitFor(() => expect(result.current.edits[l.id]).toEqual({ moq: 100 }));
    // hasRowEdit's own contract (lib suite) says this row now counts towards Save.
    expect(result.current.saveCount).toBe(1);
  });

  it('a later patch on the same row merges rather than replaces', async () => {
    const l = line();
    const { result } = renderHook(() => usePlanEdits('run-1', [l], {}), { wrapper });

    act(() => result.current.setRowEdit(l, { moq: 100 }));
    act(() => result.current.setRowEdit(l, { level: 50 }));

    await waitFor(() => expect(result.current.edits[l.id]).toEqual({ moq: 100, level: 50 }));
  });

  it('resetRow drops the draft entirely - "Use suggestion" is the absence of an edit', async () => {
    const l = line();
    const { result } = renderHook(() => usePlanEdits('run-1', [l], {}), { wrapper });

    act(() => result.current.setRowEdit(l, { moq: 100 }));
    await waitFor(() => expect(result.current.saveCount).toBe(1));

    act(() => result.current.resetRow(l));
    await waitFor(() => expect(result.current.saveCount).toBe(0));
    expect(result.current.edits[l.id]).toBeUndefined();
  });
});

describe('usePlanEdits - Save (N) counts DISTINCT products (R14/E4)', () => {
  it('a grouped row with 3 member recs, edited once, counts 1 - never 3', async () => {
    const grouped = groupPlanLinesByChannel([
      line({ id: 'r1', warehouse_id: 'w1', warehouse_code: 'BRW' }),
      line({ id: 'r2', warehouse_id: 'w2', warehouse_code: 'BRW-BB' }),
      line({ id: 'r3', warehouse_id: 'w3', warehouse_code: 'BRW-AM' }),
    ]);
    const groupRow = grouped.find((l) => l.id.startsWith('group:')) as PlanLine;

    const { result } = renderHook(() => usePlanEdits('run-1', grouped, {}), { wrapper });
    act(() => result.current.setRowEdit(groupRow, { decision: { buy: 90 } }));

    await waitFor(() => expect(result.current.saveCount).toBe(1));
  });

  it('two products edited independently count as two', async () => {
    const lines = [
      line({ id: 'r1', product_id: 'p1' }),
      line({ id: 'r2', product_id: 'p2', sku: 'SKU-2' }),
    ];
    const { result } = renderHook(() => usePlanEdits('run-1', lines, {}), { wrapper });

    act(() => result.current.setRowEdit(lines[0], { moq: 5 }));
    act(() => result.current.setRowEdit(lines[1], { lifecycle: 'discontinue' }));

    await waitFor(() => expect(result.current.saveCount).toBe(2));
  });
});

describe('usePlanEdits - save() fans one edit out to every member rec (E2)', () => {
  it('a grouped row PUTs one row per member recommendation id, same fields on each', async () => {
    const grouped = groupPlanLinesByChannel([
      line({ id: 'r1', warehouse_id: 'w1', warehouse_code: 'BRW' }),
      line({ id: 'r2', warehouse_id: 'w2', warehouse_code: 'BRW-BB' }),
      line({ id: 'r3', warehouse_id: 'w3', warehouse_code: 'BRW-AM' }),
    ]);
    const groupRow = grouped.find((l) => l.id.startsWith('group:')) as PlanLine;

    const { result } = renderHook(() => usePlanEdits('run-1', grouped, {}), { wrapper });
    act(() => result.current.setRowEdit(groupRow, { moq: 40 }));

    await act(async () => {
      await result.current.save();
    });

    expect(savePlanEdits).toHaveBeenCalledTimes(1);
    const [runId, rows] = savePlanEdits.mock.calls[0];
    expect(runId).toBe('run-1');
    expect(rows.map((r: { rec_id: string }) => r.rec_id).sort()).toEqual(['r1', 'r2', 'r3']);
    for (const row of rows) {
      expect(row.moq).toBe(40);
    }
    // The synthetic group id is never sent - it names no real recommendation.
    expect(rows.some((r: { rec_id: string }) => r.rec_id.startsWith('group:'))).toBe(false);
  });

  it('an ungrouped row PUTs exactly one row, under its own rec id', async () => {
    const l = line();
    const { result } = renderHook(() => usePlanEdits('run-1', [l], {}), { wrapper });
    act(() => result.current.setRowEdit(l, { level: 12 }));

    await act(async () => {
      await result.current.save();
    });

    const [, rows] = savePlanEdits.mock.calls[0];
    expect(rows).toHaveLength(1);
    expect(rows[0].rec_id).toBe('r1');
    expect(rows[0].level).toBe(12);
  });

  it('save() with nothing drafted never calls the service at all', async () => {
    const l = line();
    const { result } = renderHook(() => usePlanEdits('run-1', [l], {}), { wrapper });

    await act(async () => {
      await result.current.save();
    });

    expect(savePlanEdits).not.toHaveBeenCalled();
  });
});

describe('usePlanEdits - absent-vs-null contract (E1)', () => {
  it('an untouched field is ABSENT from the row, a cleared one is sent as null', async () => {
    const l = line();
    const { result } = renderHook(() => usePlanEdits('run-1', [l], {}), { wrapper });

    // Only MOQ is touched, and touched by CLEARING it (withdrawing an override).
    act(() => result.current.setRowEdit(l, { moq: null }));

    await act(async () => {
      await result.current.save();
    });

    const [, rows] = savePlanEdits.mock.calls[0];
    const row = rows[0];
    expect(row.moq).toBeNull();
    expect('decision' in row).toBe(false);
    expect('level' in row).toBe(false);
    expect('reorder_qty' in row).toBe(false);
    expect('lifecycle' in row).toBe(false);
  });

  it('a level of 0 (falsy but set) still rides as 0, never dropped as if absent', async () => {
    const l = line();
    const { result } = renderHook(() => usePlanEdits('run-1', [l], {}), { wrapper });

    act(() => result.current.setRowEdit(l, { level: 0 }));

    await act(async () => {
      await result.current.save();
    });

    const [, rows] = savePlanEdits.mock.calls[0];
    expect(rows[0].level).toBe(0);
  });
});

describe('usePlanEdits - Confirm saves first, then confirms (order asserted, E3)', () => {
  it('save runs to completion before confirm-decisions is ever called', async () => {
    const l = line();
    const order: string[] = [];
    savePlanEdits.mockImplementation(async () => {
      order.push('save');
      return { saved_rows: 1, saved_products: 1 };
    });
    confirmDecisions.mockImplementation(async () => {
      order.push('confirm');
      return { confirmed_count: 1, po_count: 1 };
    });

    const { result } = renderHook(() => usePlanEdits('run-1', [l], {}), { wrapper });
    act(() => result.current.setRowEdit(l, { moq: 5 }));

    await act(async () => {
      await result.current.confirm();
    });

    expect(order).toEqual(['save', 'confirm']);
  });

  it('confirm still confirms when there is nothing drafted - save is a no-op, not skipped', async () => {
    const l = line();
    const { result } = renderHook(() => usePlanEdits('run-1', [l], {}), { wrapper });

    await act(async () => {
      await result.current.confirm();
    });

    expect(savePlanEdits).not.toHaveBeenCalled();
    expect(confirmDecisions).toHaveBeenCalledWith('run-1', []);
  });
});

describe('usePlanEdits - beforeunload is armed only while drafts exist (D7)', () => {
  it('registers no listener while the draft map is empty', () => {
    const addSpy = vi.spyOn(window, 'addEventListener');
    const l = line();
    renderHook(() => usePlanEdits('run-1', [l], {}), { wrapper });

    expect(addSpy.mock.calls.some(([evt]) => evt === 'beforeunload')).toBe(false);
    addSpy.mockRestore();
  });

  it('arms beforeunload the moment a row is edited', async () => {
    const addSpy = vi.spyOn(window, 'addEventListener');
    const l = line();
    const { result } = renderHook(() => usePlanEdits('run-1', [l], {}), { wrapper });

    act(() => result.current.setRowEdit(l, { moq: 5 }));

    await waitFor(() =>
      expect(addSpy.mock.calls.some(([evt]) => evt === 'beforeunload')).toBe(true),
    );
    addSpy.mockRestore();
  });

  it('disarms it again once the drafts clear (e.g. after Save)', async () => {
    const removeSpy = vi.spyOn(window, 'removeEventListener');
    const l = line();
    const { result } = renderHook(() => usePlanEdits('run-1', [l], {}), { wrapper });

    act(() => result.current.setRowEdit(l, { moq: 5 }));
    await waitFor(() => expect(result.current.saveCount).toBe(1));

    await act(async () => {
      await result.current.save();
    });

    await waitFor(() => expect(result.current.saveCount).toBe(0));
    expect(removeSpy.mock.calls.some(([evt]) => evt === 'beforeunload')).toBe(true);
    removeSpy.mockRestore();
  });
});

describe('usePlanEdits - confirmable summary reflects the draft map live', () => {
  it('reads a fresh ConfirmSummary once an edit lands, without waiting on a save', async () => {
    const l = line({ order_qty: 10, unit_cost: 10, cash_impact: 100 });
    const decisions: PlanDecisionMap = {};
    const { result } = renderHook(() => usePlanEdits('run-1', [l], decisions), { wrapper });

    expect(result.current.confirmable.products).toBe(1);

    act(() => result.current.setRowEdit(l, { decision: { skip: true } }));

    await waitFor(() => expect(result.current.confirmable.products).toBe(0));
  });
});
