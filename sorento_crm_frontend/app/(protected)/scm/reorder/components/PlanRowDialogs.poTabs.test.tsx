/**
 * S2 (PLAN-po-spo-site-pool-and-order-sheet-downloads, AC-11): a PRODUCT-grain row
 * carries no pool code (`pool_warehouse_code: null`, ungrouped with `warehouse_code:
 * null`) - `poolLocationLabel` already returns `null` for it (`PlanRowDialogs.test.tsx`
 * pins that separately). Today `PoTabs` calls `getPoHistoryToPool(runId, productId,
 * null)` regardless, but the SERVICE function short-circuits on a falsy
 * `warehouseCode` (`if (!runId || !productId || !warehouseCode) return { history: [] }`)
 * and never calls `apiFetch` at all - so the History tab is 0 BY CONSTRUCTION, never by
 * an actual empty answer from the backend.
 *
 * Two things pinned here:
 *  1. `PoTabs` itself never skips the call and never appends a "to <pool>" suffix when
 *     there is no pool to name (component level, `getPoHistoryToPool` mocked).
 *  2. `getPoHistoryToPool` itself must still reach the network on a null pool - the read
 *     without a `warehouse` param the backend's AC-10 promises (service level, `apiFetch`
 *     mocked instead, the real service function under test).
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReorderRecommendation } from '../types/reorder.types';
import { recToPlanLine, type PlanLine } from '../lib/planLine';
import { PlanRowDialog } from './PlanRowDialogs';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {},
    addListener() {}, removeListener() {},
  });
}

function rec(over: Partial<ReorderRecommendation> = {}): ReorderRecommendation {
  return {
    id: 'r1', type: 'buy', sku: 'SKU-1', product_name: 'Product one',
    abc_class: null, xyz_class: null, warehouse_code: null, warehouse_name: null,
    product_id: 'p1', warehouse_id: null, is_network: true, allocation: null,
    order_qty: 23, recommended_qty: 23, reorder_point: 0, min_qty: null, max_qty: null,
    order_up_to: 0, net_position: -23, days_of_cover: null, reason: 'reorder_level',
    reason_label: '', confidence: 'low', sample_size: 0,
    supplier: { supplier_code: 'S1', supplier_name: 'Acme', unit_cost: 10,
                lead_time_days: 30, composite_score: 0, is_primary: true },
    alternatives: [], is_exception: false, disposition_action: null, transfer_flag: null,
    forecast_daily_demand: 0, lead_time_days: 30, lead_time_source: 'default',
    safety_stock: 0, safety_stock_method: null, safety_stock_fallback: null,
    service_level: null, safety_days: 0, review_days: 0,
    moq: null, master_moq: null, moq_is_override: false,
    order_multiple: null, policy_type: 'reorder_level', supplier_selection: 'primary',
    unit_cost: 10, cash_impact: 230, rank: 1, rank_score: 0, funding_status: null,
    days_to_stockout: null, rank_factors: [],
    on_hand: 1, incoming_spo: 0, outstanding_po: 0, outstanding_sales: 24,
    project_committed: 0, retail_committed: 24,
    // The product-grain shape itself: no location, so no pool to name.
    segment: null, pool_warehouse_id: null, pool_warehouse_code: null,
    ...over,
  } as ReorderRecommendation;
}

const line = (over: Partial<ReorderRecommendation> = {}): PlanLine => recToPlanLine(rec(over));

// =========================================================================== #
// 1. PoTabs (component) - never skips the call, never appends "to <pool>"
// =========================================================================== #

const getSpoHistory = vi.fn();
const getPoHistoryToPool = vi.fn();
vi.mock('../services/planEditsService', () => ({
  getSpoHistory: (...a: unknown[]) => getSpoHistory(...a),
  getPoHistoryToPool: (...a: unknown[]) => getPoHistoryToPool(...a),
}));

// The row-expand documents panel is its own suite; here it only has to exist so the
// On-hand table's row-click branch (imported transitively) never throws.
vi.mock('../../../project-sales/fulfilment-planning/components/StockDocumentsPanel', () => ({
  StockDocumentsPanel: () => <div data-testid="stock-documents-panel" />,
}));

describe('PoTabs on a product-grain line (AC-11, component level)', () => {
  function renderPoDialog(l: PlanLine) {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return render(
      <QueryClientProvider client={client}>
        <PlanRowDialog
          request={{ kind: 'po', line: l }}
          onOpenChange={() => {}}
          runId="run-1"
          poReceipts={[]}
        />
      </QueryClientProvider>,
    );
  }

  it('calls getPoHistoryToPool with a null pool code instead of skipping the call', async () => {
    getPoHistoryToPool.mockResolvedValue({
      history: [{
        po_number: 'PO-90', supplier_name: 'Acme', qty: 30, unit_cost: 9.5, currency: 'MYR',
        issued_at: '2026-07-01', eta: '2026-07-20', status: 'received',
      }],
    });
    renderPoDialog(line());

    fireEvent.mouseDown(await screen.findByText('History (1)'));

    expect(getPoHistoryToPool).toHaveBeenCalledWith('run-1', 'p1', null);
    // The History tab is no longer 0 by construction - a real line reaches the table.
    expect(await screen.findByText('PO-90')).toBeInTheDocument();
  });

  it('Open/History tab labels carry no "to <pool>" suffix when the row has none to name', async () => {
    getPoHistoryToPool.mockResolvedValue({ history: [] });
    renderPoDialog(line());

    expect(await screen.findByText('Open (0)')).toBeInTheDocument();
    expect(screen.getByText('History (0)')).toBeInTheDocument();
    expect(screen.queryByText(/^Open to /)).not.toBeInTheDocument();
    expect(screen.queryByText(/^History to /)).not.toBeInTheDocument();
  });

  it('the dialog title names no pool either, for the same reason', () => {
    getPoHistoryToPool.mockResolvedValue({ history: [] });
    renderPoDialog(line());
    expect(screen.getByText('PO - SKU-1')).toBeInTheDocument();
  });
});

// =========================================================================== #
// 2. getPoHistoryToPool (service) - the real defect: a null pool must still fetch
// =========================================================================== #

describe('getPoHistoryToPool on a null pool code (AC-11, service level)', () => {
  it('still calls apiFetch, against purchase-trend with NO warehouse param', async () => {
    vi.resetModules();
    const apiFetch = vi.fn().mockResolvedValue({
      ok: true,
      headers: { get: () => 'application/json' },
      json: async () => ({ products: { p1: { lines: [] } } }),
    });
    vi.doMock('@/lib/api', () => ({ apiFetch }));

    const { getPoHistoryToPool: realGetPoHistoryToPool } = await import(
      '../services/planEditsService'
    );

    await realGetPoHistoryToPool('run-1', 'p1', null);

    expect(apiFetch).toHaveBeenCalledTimes(1);
    const [url] = apiFetch.mock.calls[0] as [string];
    const parsed = new URL(url, 'http://x');
    expect(parsed.pathname).toBe('/api/v1/scm/reorder-runs/run-1/purchase-trend');
    expect(parsed.searchParams.has('warehouse')).toBe(false);

    vi.doUnmock('@/lib/api');
  });
});
