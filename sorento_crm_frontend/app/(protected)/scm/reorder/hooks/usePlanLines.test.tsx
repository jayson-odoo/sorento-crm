/**
 * usePlanLines - the purchase-trend fetch is LAZY (Fix 5, 2026-08-12), unlike every
 * other fetch this hook merges. Eagerly fetching it for every product on plan mount
 * was pure waste: the PO cell's popover is the only place it is read, and most rows on
 * a plan never have that popover opened. `requestPurchaseTrend()` flips a "wanted"
 * flag once the first popover opens; react-query caches the response the normal way
 * after that, so a second popover on the same run is free.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const getBuyRecommendationsForCash = vi.fn();
const getCoveredRecommendations = vi.fn();
const getNeedsLevelRecommendations = vi.fn();
const getAllDispositionRecommendations = vi.fn();
const getCoverSources = vi.fn();
const getPriceHistory = vi.fn();
const getTrajectory = vi.fn();
const getLevelSuggestions = vi.fn();
const getPurchaseTrend = vi.fn();
const getPoBook = vi.fn();
const getProductEconomics = vi.fn();
const getProductImages = vi.fn();
const amendLevelSuggestion = vi.fn();
const recordLifecycleDecision = vi.fn();
const setMoqOverride = vi.fn();

// S16: a tiny in-memory store standing in for the backend's own `plan_row_decision`
// table - `recordPlanRowDecision`/`clearPlanRowDecision` write it, `getPlanRowDecisions`
// (what `usePlanLines`' own query reads after every write invalidates it) reads it back,
// the same round trip the real endpoints make.
let planRowDecisionsStore: Array<{
  recommendation_id: string;
  kind: string;
  buy_qty: number | null;
  stock_takes: Array<{ location: string; location_name: string | null; qty: number }>;
  po_qty: number | null;
  po_refs: string[];
  reason_text: string | null;
  price_mode?: string;
  supplier_code?: string | null;
  supplier_name?: string | null;
  unit_cost?: number | null;
  lead_time_days?: number | null;
  draft_po_number: string | null;
  draft_po_id: string | null;
}> = [];
const recordPlanRowDecision = vi.fn(
  async (
    recId: string,
    payload: {
      kind: string;
      buy_qty?: number;
      stock_takes?: Array<{ location: string; qty: number }>;
      po_qty?: number;
      po_refs?: string[];
      reason_text?: string;
    },
  ) => {
    const entry = {
      recommendation_id: recId,
      kind: payload.kind,
      buy_qty: payload.buy_qty ?? null,
      stock_takes: (payload.stock_takes ?? []).map((t) => ({
        location: t.location,
        location_name: null,
        qty: t.qty,
      })),
      po_qty: payload.po_qty ?? null,
      po_refs: payload.po_refs ?? [],
      reason_text: payload.reason_text ?? null,
      draft_po_number: null,
      draft_po_id: null,
    };
    planRowDecisionsStore = [
      ...planRowDecisionsStore.filter((d) => d.recommendation_id !== recId),
      entry,
    ];
    return entry;
  },
);
const clearPlanRowDecision = vi.fn(async (recId: string) => {
  planRowDecisionsStore = planRowDecisionsStore.filter((d) => d.recommendation_id !== recId);
  return { cleared: true };
});
const getPlanRowDecisions = vi.fn(async () => ({
  data: planRowDecisionsStore,
  decided_count: planRowDecisionsStore.length,
  total_count: planRowDecisionsStore.length,
}));

vi.mock('../services/reorderRunService', () => ({
  getBuyRecommendationsForCash: (...a: unknown[]) => getBuyRecommendationsForCash(...a),
  getCoveredRecommendations: (...a: unknown[]) => getCoveredRecommendations(...a),
  getNeedsLevelRecommendations: (...a: unknown[]) => getNeedsLevelRecommendations(...a),
  getAllDispositionRecommendations: (...a: unknown[]) => getAllDispositionRecommendations(...a),
  getCoverSources: (...a: unknown[]) => getCoverSources(...a),
  getPriceHistory: (...a: unknown[]) => getPriceHistory(...a),
  getTrajectory: (...a: unknown[]) => getTrajectory(...a),
  getLevelSuggestions: (...a: unknown[]) => getLevelSuggestions(...a),
  getPurchaseTrend: (...a: unknown[]) => getPurchaseTrend(...a),
  getPoBook: (...a: unknown[]) => getPoBook(...a),
  getProductEconomics: (...a: unknown[]) => getProductEconomics(...a),
  getProductImages: (...a: unknown[]) => getProductImages(...a),
  amendLevelSuggestion: (...a: unknown[]) => amendLevelSuggestion(...a),
  recordLifecycleDecision: (...a: unknown[]) => recordLifecycleDecision(...a),
  setMoqOverride: (...a: unknown[]) => setMoqOverride(...a),
  recordPlanRowDecision: (recId: string, payload: never) => recordPlanRowDecision(recId, payload),
  clearPlanRowDecision: (recId: string) => clearPlanRowDecision(recId),
  getPlanRowDecisions: () => getPlanRowDecisions(),
}));

import { usePlanLines } from './usePlanLines';
import { applySourceEdits } from '../lib/coverPlan';

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return React.createElement(QueryClientProvider, { client }, children);
}

beforeEach(() => {
  getBuyRecommendationsForCash.mockReset().mockResolvedValue([]);
  getCoveredRecommendations.mockReset().mockResolvedValue([]);
  getNeedsLevelRecommendations.mockReset().mockResolvedValue([]);
  getAllDispositionRecommendations.mockReset().mockResolvedValue([]);
  getCoverSources.mockReset().mockResolvedValue({ sources: {}, cover_scope: 'all_locations' });
  getPriceHistory.mockReset().mockResolvedValue({ prices: {}, movement_threshold_pct: 5, stale_after_days: 180 });
  getTrajectory.mockReset().mockResolvedValue({ series: {} });
  getLevelSuggestions.mockReset().mockResolvedValue({ suggestions: {} });
  getPurchaseTrend.mockReset().mockResolvedValue({ window_months: 3, products: {} });
  getPoBook.mockReset().mockResolvedValue({ po_book: {} });
  getProductEconomics.mockReset().mockResolvedValue({ products: {}, thresholds: {} });
  getProductImages.mockReset().mockResolvedValue({ has_image: {} });
  amendLevelSuggestion.mockReset().mockResolvedValue(undefined);
  recordLifecycleDecision.mockReset().mockResolvedValue(undefined);
  setMoqOverride.mockReset().mockResolvedValue({
    recommendation_id: 'r1', moq: null, moq_is_override: false, master_moq: null,
    order_qty: null, recommended_qty: null, cash_impact: null,
  });
  planRowDecisionsStore = [];
  recordPlanRowDecision.mockClear();
  clearPlanRowDecision.mockClear();
  getPlanRowDecisions.mockClear();
});

describe('usePlanLines - purchase trend is lazy, not eager', () => {
  it('does NOT fetch the purchase trend on mount, even though every other fetch runs', async () => {
    renderHook(() => usePlanLines('run-1', true), { wrapper });

    await waitFor(() => expect(getBuyRecommendationsForCash).toHaveBeenCalledWith('run-1'));
    expect(getCoveredRecommendations).toHaveBeenCalledWith('run-1');
    expect(getNeedsLevelRecommendations).toHaveBeenCalledWith('run-1');
    expect(getAllDispositionRecommendations).toHaveBeenCalledWith('run-1');
    expect(getPurchaseTrend).not.toHaveBeenCalled();
  });

  it('fetches the purchase trend once requestPurchaseTrend() is called', async () => {
    const { result } = renderHook(() => usePlanLines('run-1', true), { wrapper });
    await waitFor(() => expect(getBuyRecommendationsForCash).toHaveBeenCalled());
    expect(getPurchaseTrend).not.toHaveBeenCalled();

    act(() => result.current.requestPurchaseTrend());

    await waitFor(() => expect(getPurchaseTrend).toHaveBeenCalledWith('run-1'));
  });

  it('never re-fetches on a second requestPurchaseTrend() call - the cached response stands', async () => {
    const { result } = renderHook(() => usePlanLines('run-1', true), { wrapper });
    await waitFor(() => expect(getBuyRecommendationsForCash).toHaveBeenCalled());

    act(() => result.current.requestPurchaseTrend());
    await waitFor(() => expect(getPurchaseTrend).toHaveBeenCalledTimes(1));

    act(() => result.current.requestPurchaseTrend());
    expect(getPurchaseTrend).toHaveBeenCalledTimes(1);
  });

  it('never fetches the purchase trend at all when the run is disabled', () => {
    renderHook(() => usePlanLines(null, false), { wrapper });
    expect(getPurchaseTrend).not.toHaveBeenCalled();
    expect(getBuyRecommendationsForCash).not.toHaveBeenCalled();
  });
});

/**
 * A decision spends only what its OWN row needed (review finding 2, round 2).
 *
 * The pool is shared: `takenByProduct` subtracts every decided source from what the next row
 * of the same product is offered. A cover edit that was clamped to the source's free stock but
 * not to the row's own gap therefore reserved units this row could never use, and the next row
 * was told they were gone.
 */
describe('usePlanLines - one row cannot reserve stock it does not need', () => {
  function buyRec(over: Record<string, unknown> = {}) {
    return {
      id: 'r1', type: 'buy', sku: 'SKU-1', product_name: 'Product one',
      abc_class: null, xyz_class: null, warehouse_code: 'DC1', warehouse_name: 'DC1',
      product_id: 'p1', warehouse_id: 'wh-DC1', is_network: false, allocation: null,
      order_qty: 10, recommended_qty: 10, reorder_point: 10, min_qty: null, max_qty: null,
      order_up_to: 20, net_position: -10, days_of_cover: null, reason: 'reorder_point',
      reason_label: '', confidence: 'low', sample_size: 0,
      supplier: { supplier_code: 'S1', supplier_name: 'Acme', unit_cost: 10,
                  lead_time_days: 30, composite_score: 0, is_primary: true },
      alternatives: [], is_exception: false, disposition_action: null, transfer_flag: null,
      forecast_daily_demand: 1, lead_time_days: 30, lead_time_source: 'default',
      safety_stock: 0, safety_stock_method: null, safety_stock_fallback: null,
      service_level: null, safety_days: 0, review_days: 30, demand_window_days: 90,
      moq: null, order_multiple: null, policy_type: 'reorder_point', supplier_selection: 'primary',
      unit_cost: 10, cash_impact: 100, rank: 1, rank_score: 0, funding_status: null,
      days_to_stockout: null, rank_factors: [], segment: 'project',
      on_hand: 0, incoming_spo: 0, outstanding_po: 0, outstanding_sales: 10,
      reorder_level: null, master_reorder_level: null,
      ...over,
    };
  }

  it('leaves the next row the stock the first row never needed', async () => {
    getBuyRecommendationsForCash.mockResolvedValue([
      buyRec(),
      buyRec({ id: 'r2', warehouse_code: 'PJ', warehouse_id: 'wh-PJ', rank: 2 }),
    ]);
    getCoverSources.mockResolvedValue({
      sources: {
        // A site pool: after R18 a project bin is never offered as a source.
        p1: [{ warehouse_id: 'wh-MWH', warehouse_code: 'MWH', segment: 'dealer', qty: 50 }],
      },
      cover_scope: 'all_locations',
    });

    const { result } = renderHook(() => usePlanLines('run-1', true), { wrapper });
    await waitFor(() => expect(result.current.lines).toHaveLength(2));

    const first = result.current.lines.find((l) => l.id === 'r1')!;
    // The buyer types 40 into a location holding 50, against a gap of 10.
    const edited = applySourceEdits(result.current.coverFor(first), { 'wh-MWH': 40 });
    expect(edited.coverQty).toBe(10);
    await act(async () => {
      await result.current.decide(first, {
        stock: {
          qty: edited.coverQty,
          sources: edited.sources.map((s) => ({
            warehouse_id: s.warehouse_id,
            warehouse_code: s.warehouse_code,
            qty: s.qty,
          })),
        },
      });
    });
    await waitFor(() => expect(result.current.decisions.r1).toBeDefined());

    const second = result.current.lines.find((l) => l.id === 'r2')!;
    // 50 free less the 10 the first row actually took, never less the 40 it typed.
    expect(result.current.coverFor(second).offered.map((s) => s.qty)).toEqual([40]);
  });
});

/**
 * P8: "Use PO" is a retail answer, never a project one.
 *
 * The backend already keeps a project-only cell out of the `po_book` map. This is the other
 * half of the same decision, and the half that matters on a GROUPED row: a product whose
 * project bin and dealer bin are summed together must still show the dealer bin's receipts
 * while showing none of the project bin's.
 */
describe('usePlanLines - poFor never offers a project row a purchase order', () => {
  function row(over: Record<string, unknown> = {}) {
    return {
      id: 'r1', type: 'buy', sku: 'SKU-1', product_name: 'Product one',
      abc_class: null, xyz_class: null, warehouse_code: 'DC1', warehouse_name: 'DC1',
      product_id: 'p1', warehouse_id: 'wh-DC1', is_network: false, allocation: null,
      order_qty: 10, recommended_qty: 10, reorder_point: 10, min_qty: null, max_qty: null,
      order_up_to: 20, net_position: -10, days_of_cover: null, reason: 'reorder_point',
      reason_label: '', confidence: 'low', sample_size: 0,
      supplier: { supplier_code: 'S1', supplier_name: 'Acme', unit_cost: 10,
                  lead_time_days: 30, composite_score: 0, is_primary: true },
      alternatives: [], is_exception: false, disposition_action: null, transfer_flag: null,
      forecast_daily_demand: 1, lead_time_days: 30, lead_time_source: 'default',
      safety_stock: 0, safety_stock_method: null, safety_stock_fallback: null,
      service_level: null, safety_days: 0, review_days: 30, demand_window_days: 90,
      moq: null, order_multiple: null, policy_type: 'reorder_point',
      supplier_selection: 'primary', unit_cost: 10, cash_impact: 100, rank: 1,
      rank_score: 0, funding_status: null, days_to_stockout: null, rank_factors: [],
      segment: 'dealer', on_hand: 0, incoming_spo: 0, outstanding_po: 0,
      outstanding_sales: 10, reorder_level: null, master_reorder_level: null,
      project_committed: 0, retail_committed: 10,
      ...over,
    };
  }

  const receipt = { po_number: 'PO-1', status: 'active', expected_date: null, remaining: 20 };

  it('serves the receipts of a retail row', async () => {
    getBuyRecommendationsForCash.mockResolvedValue([row()]);
    getPoBook.mockResolvedValue({ po_book: { 'p1:wh-DC1': [receipt] } });

    const { result } = renderHook(() => usePlanLines('run-1', true), { wrapper });
    await waitFor(() => expect(result.current.lines).toHaveLength(1));

    expect(result.current.poFor(result.current.lines[0])).toHaveLength(1);
  });

  it('serves none to a project row, even when the map still carries its key', async () => {
    getBuyRecommendationsForCash.mockResolvedValue([
      row({ project_committed: 9857, retail_committed: 0 }),
    ]);
    getPoBook.mockResolvedValue({ po_book: { 'p1:wh-DC1': [receipt] } });

    const { result } = renderHook(() => usePlanLines('run-1', true), { wrapper });
    await waitFor(() => expect(result.current.lines).toHaveLength(1));

    expect(result.current.poFor(result.current.lines[0])).toEqual([]);
  });
});

describe('usePlanLines - the photo map is lazy too, and one call for the whole run (AC-7)', () => {
  it('does NOT fetch the photos on mount', async () => {
    renderHook(() => usePlanLines('run-1', true), { wrapper });

    await waitFor(() => expect(getBuyRecommendationsForCash).toHaveBeenCalledWith('run-1'));
    expect(getProductImages).not.toHaveBeenCalled();
  });

  it('fetches them once, on the first icon opened, however many rows ask', async () => {
    const { result } = renderHook(() => usePlanLines('run-1', true), { wrapper });
    await waitFor(() => expect(getBuyRecommendationsForCash).toHaveBeenCalled());

    act(() => result.current.requestProductImages());
    await waitFor(() => expect(getProductImages).toHaveBeenCalledWith('run-1'));

    act(() => result.current.requestProductImages());
    expect(getProductImages).toHaveBeenCalledTimes(1);
  });

  it('reports idle until asked, then ready, and says which products have a photo', async () => {
    getProductImages.mockResolvedValue({ has_image: { p1: true } });
    const { result } = renderHook(() => usePlanLines('run-1', true), { wrapper });
    await waitFor(() => expect(getBuyRecommendationsForCash).toHaveBeenCalled());

    expect(result.current.photoStatus).toBe('idle');

    act(() => result.current.requestProductImages());
    await waitFor(() => expect(result.current.photoStatus).toBe('ready'));

    const withPhoto = { product_id: 'p1' } as never;
    const without = { product_id: 'p2' } as never;
    expect(result.current.hasPhotoFor(withPhoto)).toBe(true);
    expect(result.current.hasPhotoFor(without)).toBe(false);
  });

  it('a failed photo fetch is reported, and never takes the plan down with it', async () => {
    getProductImages.mockRejectedValue(new Error('boom'));
    const { result } = renderHook(() => usePlanLines('run-1', true), { wrapper });
    await waitFor(() => expect(getBuyRecommendationsForCash).toHaveBeenCalled());

    act(() => result.current.requestProductImages());

    await waitFor(() => expect(result.current.photoStatus).toBe('error'));
    expect(result.current.isError).toBe(false);
  });
});

/**
 * 20 Aug live test (commit cefa08670): the buyer's own MoQ. An ungrouped row writes its
 * own single recommendation; a grouped PRODUCT row writes the SAME override to every
 * member (MoQ is a supplier/product fact, not a per-location one - `planLineGrouping.ts`).
 * Either way the write must invalidate the buy/covered fetches so a fresh page load and
 * this session never drift apart.
 */
describe('usePlanLines - updateMoq (20 Aug live test)', () => {
  it('an ungrouped row writes exactly one recommendation', async () => {
    const { result } = renderHook(() => usePlanLines('run-1', true), { wrapper });
    await waitFor(() => expect(getBuyRecommendationsForCash).toHaveBeenCalled());

    const line = { rec: { id: 'r1' } } as never;
    await act(async () => {
      await result.current.updateMoq(line, 15);
    });

    expect(setMoqOverride).toHaveBeenCalledTimes(1);
    expect(setMoqOverride).toHaveBeenCalledWith('r1', 15);
  });

  it('a grouped product row writes the same override to every member', async () => {
    const { result } = renderHook(() => usePlanLines('run-1', true), { wrapper });
    await waitFor(() => expect(getBuyRecommendationsForCash).toHaveBeenCalled());

    const grouped = {
      rec: { id: 'group-p1' },
      __group: {
        members: [{ rec: { id: 'r1' } }, { rec: { id: 'r2' } }, { rec: { id: 'r3' } }],
      },
    } as never;
    await act(async () => {
      await result.current.updateMoq(grouped, 15);
    });

    expect(setMoqOverride).toHaveBeenCalledTimes(3);
    expect(setMoqOverride).toHaveBeenCalledWith('r1', 15);
    expect(setMoqOverride).toHaveBeenCalledWith('r2', 15);
    expect(setMoqOverride).toHaveBeenCalledWith('r3', 15);
    // never the synthetic group row's own id - it is not a real recommendation
    expect(setMoqOverride).not.toHaveBeenCalledWith('group-p1', 15);
  });

  it('clearing (null) is sent through the same way as setting a value', async () => {
    const { result } = renderHook(() => usePlanLines('run-1', true), { wrapper });
    await waitFor(() => expect(getBuyRecommendationsForCash).toHaveBeenCalled());

    const line = { rec: { id: 'r1' } } as never;
    await act(async () => {
      await result.current.updateMoq(line, null);
    });

    expect(setMoqOverride).toHaveBeenCalledWith('r1', null);
  });

  it('invalidates the buy, covered and disposition plan-lines queries so the grid refetches', async () => {
    getBuyRecommendationsForCash.mockResolvedValue([]);
    const { result } = renderHook(() => usePlanLines('run-1', true), { wrapper });
    await waitFor(() => expect(getBuyRecommendationsForCash).toHaveBeenCalledTimes(1));

    const line = { rec: { id: 'r1' } } as never;
    await act(async () => {
      await result.current.updateMoq(line, 15);
    });

    // the invalidated queries refetch - each fetch runs again beyond the initial mount.
    // `disposition` is included (fix-cluster, 20 Aug 2026, S8 nit): a disposition row's
    // own MOQ-driven figures went stale after a save until this was added.
    await waitFor(() =>
      expect(getBuyRecommendationsForCash).toHaveBeenCalledTimes(2),
    );
    await waitFor(() =>
      expect(getCoveredRecommendations).toHaveBeenCalledTimes(2),
    );
    await waitFor(() =>
      expect(getAllDispositionRecommendations).toHaveBeenCalledTimes(2),
    );
  });

  it('a single rejected write on an ungrouped row still rejects, after refreshing the grid', async () => {
    // S8: the group write is now `Promise.allSettled`, not `Promise.all` - this pins that
    // an ungrouped (single-member) failure still surfaces as a rejection for the caller
    // (the row panel's MOQ input) to report, rather than being swallowed here.
    setMoqOverride.mockReset().mockRejectedValue(new Error('Failed to save the MOQ.'));
    const { result } = renderHook(() => usePlanLines('run-1', true), { wrapper });
    await waitFor(() => expect(getBuyRecommendationsForCash).toHaveBeenCalled());

    const line = { rec: { id: 'r1' } } as never;
    await expect(
      act(async () => {
        await result.current.updateMoq(line, 15);
      }),
    ).rejects.toThrow('Failed to save the MOQ.');

    // The grid still refreshes - nothing here silently leaves the row on a stale value.
    await waitFor(() => expect(getBuyRecommendationsForCash).toHaveBeenCalledTimes(2));
  });

  it('a partial group failure is reported WITH the count, not silently averaged away', async () => {
    // S8: a grouped write is not atomic. Two of three members save; the caller must be
    // told it was partial, not just that "it failed" or - worse - nothing at all.
    setMoqOverride
      .mockReset()
      .mockResolvedValueOnce({
        recommendation_id: 'r1', moq: 15, moq_is_override: true, master_moq: 10,
        order_qty: null, recommended_qty: null, cash_impact: null,
      })
      .mockRejectedValueOnce(new Error('Network error.'))
      .mockResolvedValueOnce({
        recommendation_id: 'r3', moq: 15, moq_is_override: true, master_moq: 10,
        order_qty: null, recommended_qty: null, cash_impact: null,
      });
    const { result } = renderHook(() => usePlanLines('run-1', true), { wrapper });
    await waitFor(() => expect(getBuyRecommendationsForCash).toHaveBeenCalled());

    const grouped = {
      rec: { id: 'group-p1' },
      __group: {
        members: [{ rec: { id: 'r1' } }, { rec: { id: 'r2' } }, { rec: { id: 'r3' } }],
      },
    } as never;

    let caught: Error | undefined;
    await act(async () => {
      try {
        await result.current.updateMoq(grouped, 15);
      } catch (err) {
        caught = err as Error;
      }
    });

    expect(caught?.message).toContain('1 of 3 locations did not save');
    // The two that DID succeed are not held back by the one that failed.
    expect(setMoqOverride).toHaveBeenCalledTimes(3);
    await waitFor(() => expect(getBuyRecommendationsForCash).toHaveBeenCalledTimes(2));
  });
});

/**
 * S16 (captain, 21 Aug, 3rd time requested): the row decision itself - buy / use stock /
 * use PO / skip, or a mixture - recorded straight to the backend. `decide`/`clear` fan a
 * grouped (product-grain) row's write out to every member recommendation id, the exact
 * same `Promise.allSettled` doctrine `updateMoq` already uses (S8).
 */
describe('usePlanLines - S16 row decisions (decide/clear)', () => {
  it('an ungrouped row records exactly one recommendation, derived to the right kind', async () => {
    const { result } = renderHook(() => usePlanLines('run-1', true), { wrapper });
    await waitFor(() => expect(getBuyRecommendationsForCash).toHaveBeenCalled());

    const line = { rec: { id: 'r1' } } as never;
    await act(async () => {
      await result.current.decide(line, { buy: 23 });
    });

    expect(recordPlanRowDecision).toHaveBeenCalledTimes(1);
    expect(recordPlanRowDecision).toHaveBeenCalledWith(
      'r1',
      expect.objectContaining({ kind: 'buy', buy_qty: 23 }),
    );
    // The server round trip lands back in `decisions`, keyed by the real rec id.
    await waitFor(() => expect(result.current.decisions.r1).toEqual({ buy: 23, priceMode: 'use_last' }));
  });

  it('a grouped product row fans the SAME decision out to every member, never the synthetic group id', async () => {
    const { result } = renderHook(() => usePlanLines('run-1', true), { wrapper });
    await waitFor(() => expect(getBuyRecommendationsForCash).toHaveBeenCalled());

    const grouped = {
      rec: { id: 'group-p1' },
      __group: {
        members: [{ rec: { id: 'r1' } }, { rec: { id: 'r2' } }, { rec: { id: 'r3' } }],
      },
    } as never;
    await act(async () => {
      await result.current.decide(grouped, { buy: 12 });
    });

    expect(recordPlanRowDecision).toHaveBeenCalledTimes(3);
    for (const id of ['r1', 'r2', 'r3']) {
      expect(recordPlanRowDecision).toHaveBeenCalledWith(
        id,
        expect.objectContaining({ kind: 'buy', buy_qty: 12 }),
      );
    }
    expect(recordPlanRowDecision).not.toHaveBeenCalledWith('group-p1', expect.anything());
  });

  it('a pending price call and supplier ride into the decision when it is made (AC-R13/R14)', async () => {
    const { result } = renderHook(() => usePlanLines('run-1', true), { wrapper });
    await waitFor(() => expect(getBuyRecommendationsForCash).toHaveBeenCalled());

    const line = { id: 'r1', rec: { id: 'r1' }, supplier: { code: 'SUP-A' } } as never;
    // Changing either on an UNDECIDED row records nothing: it must not start counting as
    // decided just because its supplier changed.
    await act(async () => {
      await result.current.chooseRow(line, { priceMode: 'ask_new' });
      await result.current.chooseRow(line, { supplierCode: 'SUP-B' });
    });
    expect(recordPlanRowDecision).not.toHaveBeenCalled();
    expect(result.current.choiceFor(line)).toEqual({
      priceMode: 'ask_new',
      supplierCode: 'SUP-B',
    });

    await act(async () => {
      await result.current.decide(line, { buy: 40 });
    });

    expect(recordPlanRowDecision).toHaveBeenCalledWith(
      'r1',
      expect.objectContaining({
        kind: 'buy',
        buy_qty: 40,
        price_mode: 'ask_new',
        supplier_code: 'SUP-B',
      }),
    );
  });

  it('changing the supplier on an ALREADY decided row re-records it there and then', async () => {
    planRowDecisionsStore = [{
      recommendation_id: 'r1', kind: 'buy', buy_qty: 23, stock_takes: [], po_qty: null,
      po_refs: [], reason_text: null, price_mode: 'use_last', supplier_code: null,
      supplier_name: null, unit_cost: null, lead_time_days: null,
      draft_po_number: null, draft_po_id: null,
    }];
    const { result } = renderHook(() => usePlanLines('run-1', true), { wrapper });
    await waitFor(() => expect(result.current.decisions.r1).toBeDefined());

    const line = { id: 'r1', rec: { id: 'r1' }, supplier: { code: 'SUP-A' } } as never;
    await act(async () => {
      await result.current.chooseRow(line, { supplierCode: 'SUP-B' });
    });

    expect(recordPlanRowDecision).toHaveBeenCalledWith(
      'r1',
      expect.objectContaining({ kind: 'buy', buy_qty: 23, supplier_code: 'SUP-B' }),
    );
  });

  it('clear withdraws an ungrouped row, and refetches the decisions', async () => {
    planRowDecisionsStore = [{
      recommendation_id: 'r1', kind: 'buy', buy_qty: 23, stock_takes: [], po_qty: null,
      po_refs: [], reason_text: null, draft_po_number: null, draft_po_id: null,
    }];
    const { result } = renderHook(() => usePlanLines('run-1', true), { wrapper });
    await waitFor(() => expect(result.current.decisions.r1).toEqual({ buy: 23, priceMode: 'use_last' }));

    const line = { rec: { id: 'r1' } } as never;
    await act(async () => {
      await result.current.clear(line);
    });

    expect(clearPlanRowDecision).toHaveBeenCalledWith('r1');
    await waitFor(() => expect(result.current.decisions.r1).toBeUndefined());
  });

  it('clear fans out across a grouped row\'s members the same way decide does', async () => {
    planRowDecisionsStore = [
      { recommendation_id: 'r1', kind: 'buy', buy_qty: 12, stock_takes: [], po_qty: null, po_refs: [], reason_text: null, draft_po_number: null, draft_po_id: null },
      { recommendation_id: 'r2', kind: 'buy', buy_qty: 12, stock_takes: [], po_qty: null, po_refs: [], reason_text: null, draft_po_number: null, draft_po_id: null },
    ];
    const { result } = renderHook(() => usePlanLines('run-1', true), { wrapper });
    await waitFor(() => expect(result.current.decisions.r1).toBeDefined());

    const grouped = {
      rec: { id: 'group-p1' },
      __group: { members: [{ rec: { id: 'r1' } }, { rec: { id: 'r2' } }] },
    } as never;
    await act(async () => {
      await result.current.clear(grouped);
    });

    expect(clearPlanRowDecision).toHaveBeenCalledWith('r1');
    expect(clearPlanRowDecision).toHaveBeenCalledWith('r2');
    await waitFor(() => expect(result.current.decisions.r1).toBeUndefined());
    expect(result.current.decisions.r2).toBeUndefined();
  });

  it('a rejected write on an ungrouped row rejects for the caller to toast, after refreshing', async () => {
    recordPlanRowDecision.mockRejectedValueOnce(new Error('Failed to record the decision.'));
    const { result } = renderHook(() => usePlanLines('run-1', true), { wrapper });
    await waitFor(() => expect(getBuyRecommendationsForCash).toHaveBeenCalled());

    const line = { rec: { id: 'r1' } } as never;
    await expect(
      act(async () => {
        await result.current.decide(line, { buy: 23 });
      }),
    ).rejects.toThrow('Failed to record the decision.');
  });

  it('a partial group failure is reported WITH the count, the successes are not held back', async () => {
    recordPlanRowDecision
      .mockImplementationOnce(async (recId: string) => {
        const entry = { recommendation_id: recId, kind: 'buy', buy_qty: 12, stock_takes: [], po_qty: null, po_refs: [], reason_text: null, draft_po_number: null, draft_po_id: null };
        planRowDecisionsStore = [...planRowDecisionsStore, entry];
        return entry;
      })
      .mockRejectedValueOnce(new Error('Network error.'))
      .mockImplementationOnce(async (recId: string) => {
        const entry = { recommendation_id: recId, kind: 'buy', buy_qty: 12, stock_takes: [], po_qty: null, po_refs: [], reason_text: null, draft_po_number: null, draft_po_id: null };
        planRowDecisionsStore = [...planRowDecisionsStore, entry];
        return entry;
      });
    const { result } = renderHook(() => usePlanLines('run-1', true), { wrapper });
    await waitFor(() => expect(getBuyRecommendationsForCash).toHaveBeenCalled());

    const grouped = {
      rec: { id: 'group-p1' },
      __group: {
        members: [{ rec: { id: 'r1' } }, { rec: { id: 'r2' } }, { rec: { id: 'r3' } }],
      },
    } as never;

    let caught: Error | undefined;
    await act(async () => {
      try {
        await result.current.decide(grouped, { buy: 12 });
      } catch (err) {
        caught = err as Error;
      }
    });

    expect(caught?.message).toContain('1 of 3 locations did not save');
    expect(recordPlanRowDecision).toHaveBeenCalledTimes(3);
  });

  it('decidedCount/totalDecidableCount come straight off the server list, not off client state', async () => {
    getPlanRowDecisions.mockResolvedValue({ data: [], decided_count: 4, total_count: 9 });
    const { result } = renderHook(() => usePlanLines('run-1', true), { wrapper });

    await waitFor(() => expect(result.current.decidedCount).toBe(4));
    expect(result.current.totalDecidableCount).toBe(9);
  });

  it('deciding the SAME product at two DIFFERENT warehouses (location-grain, ungrouped) moves decidedCount by one, not two', async () => {
    // Review finding B1: two separate decide() calls (never a grouped fan-out - these
    // are two ordinary rows, not one product-grain group's members) that happen to
    // name the same product. The server counts DISTINCT product; the client-side
    // cache patch must agree, or the header reads "412 of 200 decided".
    //
    // Restored explicitly: an earlier test in this block overrides
    // `getPlanRowDecisions` with a fixed `mockResolvedValue`, which `mockClear()` in
    // `beforeEach` does not undo - this test must not inherit that override.
    getPlanRowDecisions.mockReset().mockImplementation(async () => ({
      data: planRowDecisionsStore,
      decided_count: planRowDecisionsStore.length,
      total_count: planRowDecisionsStore.length,
    }));

    function buyRec(over: Record<string, unknown> = {}) {
      return {
        id: 'r1', type: 'buy', sku: 'SKU-1', product_name: 'Product one',
        abc_class: null, xyz_class: null, warehouse_code: 'BRW', warehouse_name: 'Butterworth',
        product_id: 'p1', warehouse_id: 'wh-BRW', is_network: false, allocation: null,
        order_qty: 10, recommended_qty: 10, reorder_point: 10, min_qty: null, max_qty: null,
        order_up_to: 20, net_position: -10, days_of_cover: null, reason: 'reorder_point',
        reason_label: '', confidence: 'low', sample_size: 0,
        supplier: { supplier_code: 'S1', supplier_name: 'Acme', unit_cost: 10,
                    lead_time_days: 30, composite_score: 0, is_primary: true },
        alternatives: [], is_exception: false, disposition_action: null, transfer_flag: null,
        forecast_daily_demand: 1, lead_time_days: 30, lead_time_source: 'default',
        safety_stock: 0, safety_stock_method: null, safety_stock_fallback: null,
        service_level: null, safety_days: 0, review_days: 30, demand_window_days: 90,
        moq: null, order_multiple: null, policy_type: 'reorder_point', supplier_selection: 'primary',
        unit_cost: 10, cash_impact: 100, rank: 1, rank_score: 0, funding_status: null,
        days_to_stockout: null, rank_factors: [], segment: 'project',
        on_hand: 0, incoming_spo: 0, outstanding_po: 0, outstanding_sales: 10,
        reorder_level: null, master_reorder_level: null,
        ...over,
      };
    }
    // Both recs share product_id 'p1' (the default) - the product-grain grouping
    // never applies here, this is the plain location-grain grid.
    const recA = buyRec();
    const recB = buyRec({ id: 'r2', warehouse_code: 'PJ', warehouse_id: 'wh-PJ', rank: 2 });
    getBuyRecommendationsForCash.mockResolvedValue([recA, recB]);

    const { result } = renderHook(() => usePlanLines('run-1', true), { wrapper });
    await waitFor(() => expect(result.current.lines).toHaveLength(2));
    // The INITIAL `getPlanRowDecisions` fetch must settle before any decide()/clear()
    // call: react-query's own fetch-success handler overwrites the cache with
    // whatever it fetched regardless of an intervening `setQueryData`, so an
    // in-flight initial fetch resolving AFTER an optimistic patch would clobber it -
    // a real flake this test hit once, unrelated to the behaviour under test.
    await waitFor(() => expect(getPlanRowDecisions).toHaveBeenCalled());
    expect(result.current.decidedCount).toBe(0);

    await act(async () => {
      await result.current.decide({ id: 'r1', rec: recA } as never, { buy: 5 });
    });
    await waitFor(() => expect(result.current.decidedCount).toBe(1));

    await act(async () => {
      await result.current.decide({ id: 'r2', rec: recB } as never, { buy: 7 });
    });
    // The bug: an increment-per-call implementation reports 2 here. `waitFor`, not a
    // bare `expect`, the same as every other assertion in this test - the cache
    // notification `setQueryData` triggers lands as its own microtask outside the
    // `act()` callback's own awaited scope, one tick after `decide()`'s promise
    // itself resolves (the existing tests in this file all read the same way,
    // e.g. "an ungrouped row records exactly one recommendation").
    await waitFor(() => expect(result.current.decidedCount).toBe(1));

    // Clearing ONE of the two still-decided-elsewhere product's rows keeps the count
    // at 1 (the product is still decided via the surviving row).
    await act(async () => {
      await result.current.clear({ id: 'r1', rec: recA } as never);
    });
    await waitFor(() => expect(result.current.decidedCount).toBe(1));

    // Clearing the LAST row of the product drops it to 0.
    await act(async () => {
      await result.current.clear({ id: 'r2', rec: recB } as never);
    });
    await waitFor(() => expect(result.current.decidedCount).toBe(0));
  });
});
