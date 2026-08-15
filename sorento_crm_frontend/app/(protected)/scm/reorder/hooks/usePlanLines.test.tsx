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
const amendLevelSuggestion = vi.fn();
const recordLifecycleDecision = vi.fn();

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
  amendLevelSuggestion: (...a: unknown[]) => amendLevelSuggestion(...a),
  recordLifecycleDecision: (...a: unknown[]) => recordLifecycleDecision(...a),
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
        p1: [{ warehouse_id: 'wh-BRW-IB', warehouse_code: 'BRW-IB', segment: 'project', qty: 50 }],
      },
      cover_scope: 'all_locations',
    });

    const { result } = renderHook(() => usePlanLines('run-1', true), { wrapper });
    await waitFor(() => expect(result.current.lines).toHaveLength(2));

    const first = result.current.lines.find((l) => l.id === 'r1')!;
    // The buyer types 40 into a location holding 50, against a gap of 10.
    const edited = applySourceEdits(result.current.coverFor(first), { 'wh-BRW-IB': 40 });
    expect(edited.coverQty).toBe(10);
    act(() =>
      result.current.decide(first, {
        stock: {
          qty: edited.coverQty,
          sources: edited.sources.map((s) => ({
            warehouse_id: s.warehouse_id,
            warehouse_code: s.warehouse_code,
            qty: s.qty,
          })),
        },
      }),
    );

    const second = result.current.lines.find((l) => l.id === 'r2')!;
    // 50 free less the 10 the first row actually took, never less the 40 it typed.
    expect(result.current.coverFor(second).offered.map((s) => s.qty)).toEqual([40]);
  });
});
