/**
 * AC-S3.1 (PLAN-reorder-feedback-9sep.md, S3): the "open" tab of the project/retail demand
 * lightbox must query `scope=product` for a GROUPED (product-grain) row - the same scope the
 * history tab already passes - so the popover totals the same set of member locations the
 * grouped row's own Project/Retail cell sums. Before the fix (`PlanRowDialogs.tsx`, the open
 * `useRecommendationDemand` call) the open tab passed no scope at all and read only ONE
 * member's own location, which is the "Project 3, 0 open" mismatch the plan measured.
 *
 * Harness copied from `PlanRowDialogs.test.tsx` (the `useRecommendationDemand` mock + the
 * `renderDialog` shape) rather than imported, so this file stays a standalone red/green pin.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReorderRecommendation } from '../types/reorder.types';
import { recToPlanLine, type PlanLine } from '../lib/planLine';
import { groupPlanLinesByChannel } from '../lib/planLineGrouping';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {},
    addListener() {}, removeListener() {},
  });
}

vi.mock('../../../project-sales/fulfilment-planning/components/StockDocumentsPanel', () => ({
  StockDocumentsPanel: () => <div data-testid="stock-documents-panel" />,
}));

const useLocationStock = vi.fn();
const useRecommendationDemand = vi.fn();
vi.mock('../hooks/useReorderRun', () => ({
  useLocationStock: (...a: unknown[]) => useLocationStock(...a),
  useRecommendationDemand: (...a: unknown[]) => useRecommendationDemand(...a),
}));

vi.mock('../services/planEditsService', () => ({
  getSpoHistory: vi.fn(),
  getPoHistoryToPool: vi.fn(),
}));

import { PlanRowDialog } from './PlanRowDialogs';

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
    segment: 'dealer', pool_warehouse_id: null, pool_warehouse_code: null,
    ...over,
  } as ReorderRecommendation;
}

const line = (over: Partial<ReorderRecommendation> = {}): PlanLine => recToPlanLine(rec(over));

function renderDialog(kind: 'project' | 'retail', l: PlanLine) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <PlanRowDialog request={{ kind, line: l }} onOpenChange={() => {}} runId="run-1" />
    </QueryClientProvider>,
  );
}

const emptyDemand = { data: { lines: [], history_lines: [] }, isLoading: false };

describe('PlanRowDialog - project/retail demand scope on a grouped row (AC-S3.1)', () => {
  it('opens the OPEN tab with scope=product for a grouped row, same as the history tab', () => {
    useRecommendationDemand.mockReturnValue(emptyDemand);

    const grouped = groupPlanLinesByChannel([
      line({ id: 'r1', product_id: 'p1', warehouse_id: 'w1', warehouse_code: 'BRW' }),
      line({ id: 'r2', product_id: 'p1', warehouse_id: 'w2', warehouse_code: 'BRW-BB' }),
    ]);
    const groupRow = grouped.find((l) => l.id.startsWith('group:')) as PlanLine;

    renderDialog('project', groupRow);

    // `DemandTabs` calls the OPEN hook before the HISTORY hook (render order), and the
    // history tab already passes scope='product' today - so the discriminating check is
    // the FIRST call specifically, not "was `useRecommendationDemand` ever called with
    // scope='product'" (the history call alone would already satisfy that).
    expect(useRecommendationDemand.mock.calls[0]).toEqual(['run-1', 'r1', true, 'project', 'product']);
  });

  it('leaves an UNGROUPED row exactly as it is today - no scope on the open tab', () => {
    useRecommendationDemand.mockReturnValue(emptyDemand);

    renderDialog('project', line({ id: 'r1' }));

    expect(useRecommendationDemand).toHaveBeenCalledWith('run-1', 'r1', true, 'project');
  });
});
