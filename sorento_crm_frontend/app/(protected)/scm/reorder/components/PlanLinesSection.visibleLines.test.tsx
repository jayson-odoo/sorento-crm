/**
 * PLAN-plan-list-tile-sheet-one-scope.md, AC-5 - `visibleLines` reads the backend's
 * `rec.hidden_by_default` flag directly instead of recomputing the 12-Aug hiding rule
 * client-side (`lineBreachStatus` + `policy_type === 'reorder_level'` + not-breached).
 *
 * Today (red) `visibleLines` has no awareness of `hidden_by_default` at all - it still
 * derives its own hidden set from `lineBreachStatus(l.rec, l.net)`, which never fires for
 * an auto-basis (`reorder_point`) row regardless of the flag. Fixtures below set
 * `hidden_by_default` on an AUTO-basis line specifically so the two mechanisms disagree:
 * the old client-side rule would never hide it, the new flag-trusting rule must.
 *
 * Mocking shape copied from `PlanLinesSection.test.tsx` (`usePlanLines` + `usePlanEdits` +
 * `PlanLinesGrid` all mocked, no QueryClientProvider needed) - this file is new precisely
 * so it does not touch `PlanLinesSection.test.tsx`, which the coder is not editing for
 * this slice but which already carries the OLD (`lineBreachStatus`-driven) coverage this
 * one is going to retire in Phase 2.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, render, screen } from '@testing-library/react';
import type { PlanLine } from '../lib/planLine';
import { recToPlanLine } from '../lib/planLine';
import type { ReorderRecommendation } from '../types/reorder.types';
import type { ListQueryFilterGroup } from '@/lib/list-query/listQueryService';

const toastSuccess = vi.fn();
const toastError = vi.fn();
const toastInfo = vi.fn();
vi.mock('@/lib/toast', () => ({
  toast: {
    success: (...a: unknown[]) => toastSuccess(...a),
    error: (...a: unknown[]) => toastError(...a),
    info: (...a: unknown[]) => toastInfo(...a),
  },
}));

const usePlanLines = vi.fn();
vi.mock('../hooks/usePlanLines', () => ({ usePlanLines: (...a: unknown[]) => usePlanLines(...a) }));

const usePlanEditsMock = vi.fn();
vi.mock('../hooks/usePlanEdits', () => ({
  usePlanEdits: (...a: unknown[]) => usePlanEditsMock(...a),
}));

function stubPlanEdits(over: Record<string, unknown> = {}) {
  usePlanEditsMock.mockReturnValue({
    edits: {},
    setRowEdit: vi.fn(),
    saveRow: vi.fn(),
    savingRowIds: new Set(),
    clearAll: vi.fn(),
    saveCount: 0,
    confirmable: { products: 0, cash: 0, unpriced: 0 },
    save: vi.fn(),
    confirm: vi.fn(),
    isSaving: false,
    isConfirming: false,
    ...over,
  });
}

/**
 * AC-5b: the grid owns `filterGroup` and is expected to report the applied group upward
 * (the plan's `onFilterGroupChange` prop) - not itself under test here (`PlanLinesGrid` is
 * mocked), so the callback is captured off the props the SECTION passes down and invoked
 * directly, the same way a real grid's `useEffect(() => onFilterGroupChange?.(filterGroup),
 * [filterGroup])` would call it. `undefined` (the prop not wired yet) makes every AC-5b
 * case below red for the right reason: the call is a no-op and the grid keeps receiving
 * the default (hidden-respecting) list.
 */
let latestOnFilterGroupChange:
  | ((group: ListQueryFilterGroup | null) => void)
  | undefined;

vi.mock('./PlanLinesGrid', () => ({
  PlanLinesGrid: ({
    lines,
    onFilterGroupChange,
  }: {
    lines: PlanLine[];
    onFilterGroupChange?: (group: ListQueryFilterGroup | null) => void;
  }) => {
    latestOnFilterGroupChange = onFilterGroupChange;
    return <div>plan-lines-grid lines={lines.map((l) => l.sku).join(',')}</div>;
  },
}));
vi.mock('./PlanBudgetReview', () => ({ PlanBudgetReview: () => <div>budget-review</div> }));
vi.mock('./LevelChangesPanel', () => ({ LevelChangesPanel: () => <div>level-changes</div> }));

import { PlanLinesSection } from './PlanLinesSection';

function rec(over: Partial<ReorderRecommendation> = {}): ReorderRecommendation {
  return {
    id: 'r1', type: 'buy', sku: 'SKU-1', product_name: 'Product one',
    abc_class: null, xyz_class: null, warehouse_code: 'BRW', warehouse_name: 'Butterworth',
    product_id: 'p1', warehouse_id: 'w1', is_network: false, allocation: null,
    order_qty: 23, recommended_qty: 23, reorder_point: null, min_qty: null, max_qty: null,
    order_up_to: null, net_position: -23, days_of_cover: null, reason: 'reorder_point',
    reason_label: '', confidence: 'low', sample_size: 0,
    supplier: { supplier_code: 'S1', supplier_name: 'Acme', unit_cost: 10,
                lead_time_days: 30, composite_score: 0, is_primary: true },
    alternatives: [], is_exception: false, disposition_action: null, transfer_flag: null,
    forecast_daily_demand: 0, lead_time_days: 30, lead_time_source: 'default',
    safety_stock: 0, safety_stock_method: null, safety_stock_fallback: null,
    service_level: null, safety_days: 0, review_days: 0,
    moq: null, order_multiple: null, policy_type: 'reorder_point', supplier_selection: 'primary',
    unit_cost: 10, cash_impact: 230, rank: 1, rank_score: 0, funding_status: null,
    days_to_stockout: null, rank_factors: [],
    on_hand: 1, incoming_spo: 0, outstanding_po: 0, outstanding_sales: 24,
    reorder_level: null, master_reorder_level: null,
    // AC-1's field - not yet declared on ReorderRecommendation (the coder's concurrent
    // Phase 1 slice), passed through the `as ReorderRecommendation` cast below same as
    // every other override here. Omitted (undefined) is the THIRD case AC-5 asks for.
    ...over,
  } as ReorderRecommendation;
}

const line = (over: Partial<ReorderRecommendation> = {}): PlanLine => recToPlanLine(rec(over));

function stubPlanLines(over: Record<string, unknown> = {}) {
  usePlanLines.mockReturnValue({
    lines: [],
    decisions: {},
    decide: vi.fn(),
    clear: vi.fn(),
    totals: { decided: 0, undecided: 0, buying: 0, usingStock: 0, usingPo: 0, skipped: 0, units: 0, cost: 0, unpriced: 0 },
    decidedCount: 0,
    totalDecidableCount: 0,
    coverFor: vi.fn(),
    priceFor: vi.fn(),
    cheaperFor: vi.fn(),
    levelFor: vi.fn(),
    amendLevel: vi.fn(),
    poFor: vi.fn(),
    trendFor: vi.fn(),
    economicsFor: vi.fn(),
    healthThresholds: { margin_floor_pct: 15, dead_turnover_months: 6 },
    decideLifecycle: vi.fn(),
    staleAfterDays: 180,
    levelSuggestions: {},
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
    ...over,
  });
}

function gridSkus(): string[] {
  const text = screen.getByText(/plan-lines-grid/).textContent ?? '';
  const match = text.match(/lines=([^ ]*)/);
  return (match?.[1] ?? '').split(',').filter(Boolean);
}

beforeEach(() => {
  usePlanLines.mockReset();
  usePlanEditsMock.mockReset();
  toastSuccess.mockReset();
  toastError.mockReset();
  toastInfo.mockReset();
  stubPlanEdits();
  latestOnFilterGroupChange = undefined;
});

describe('PlanLinesSection.visibleLines - reads rec.hidden_by_default (AC-5)', () => {
  it('hides a line flagged hidden_by_default:true and shows false/undefined ones - '
    + 'even on the AUTO basis, where the old client-side breach rule never hid anything', () => {
    // AUTO basis (reorder_point) with net WAY above the reorder point: the OLD
    // `visibleLines` rule (`policy_type === 'reorder_level'`) would never touch this row
    // regardless of the flag, so today it shows - the right-reason red.
    const hidden = line({
      id: 'a', sku: 'HIDDEN-1', type: 'covered', policy_type: 'reorder_point',
      reorder_point: 50, net_position: 999,
      hidden_by_default: true,
    });
    const shownFalse = line({
      id: 'b', sku: 'SHOWN-FALSE', type: 'covered', policy_type: 'reorder_point',
      hidden_by_default: false,
    });
    const shownUndefined = line({ id: 'c', sku: 'SHOWN-UNDEF', type: 'buy' });

    stubPlanLines({ lines: [hidden, shownFalse, shownUndefined] });
    render(<PlanLinesSection runId="run-1" />);

    const skus = gridSkus();
    expect(skus).toHaveLength(2);
    expect(skus).not.toContain('HIDDEN-1');
    expect(skus).toContain('SHOWN-FALSE');
    expect(skus).toContain('SHOWN-UNDEF');
  });

  it('the "Covered by stock" status filter still shows every row, hidden_by_default or not', () => {
    const hidden = line({
      id: 'a', sku: 'HIDDEN-1', type: 'covered', policy_type: 'reorder_point',
      hidden_by_default: true,
    });
    const shownFalse = line({ id: 'b', sku: 'SHOWN-FALSE', type: 'covered', hidden_by_default: false });
    const shownUndefined = line({ id: 'c', sku: 'SHOWN-UNDEF', type: 'buy' });

    stubPlanLines({ lines: [hidden, shownFalse, shownUndefined] });
    render(
      <PlanLinesSection runId="run-1" statusFilter="covered_by_stock" onStatusFilterChange={vi.fn()} />,
    );

    const skus = gridSkus();
    expect(skus).toHaveLength(3);
    expect(skus).toContain('HIDDEN-1');
  });

  it('the "own row" exception: a product-grain hidden line (warehouse_id null) whose '
    + 'product also has a shown line stays', () => {
    const productRow = line({
      id: 'a', sku: 'SRTWT7408', product_id: 'p-srt', type: 'covered',
      warehouse_id: null, warehouse_code: null, warehouse_name: null,
      policy_type: 'reorder_point', hidden_by_default: true,
    });
    const disposition = line({
      id: 'b', sku: 'SRTWT7408', product_id: 'p-srt', type: 'disposition',
      warehouse_id: 'w-brw', warehouse_code: 'BRW',
    });

    stubPlanLines({ lines: [productRow, disposition] });
    render(<PlanLinesSection runId="run-1" />);

    // Both rows reach the grid: the product row IS the group row, the disposition sits
    // under it - dropping it left a bin disposition standing in as the plan row.
    const skus = gridSkus();
    expect(skus).toHaveLength(2);
    expect(skus).toEqual(['SRTWT7408', 'SRTWT7408']);
  });
});

/**
 * PLAN-plan-list-tile-sheet-one-scope.md, AC-5b (7e3960e38) - owner ruling 10 Sep: "better
 * to reveal them for flexibility". A Filters condition on the builder's own `rec_type`
 * field, value `covered_by_stock` (equals or `in`, at any nesting depth), makes
 * `visibleLines` hand the grid the hidden-by-default rows too - the grid reports the
 * applied group upward (`onFilterGroupChange`, not yet wired from `PlanLinesSection` at
 * this point in the lane) and the section is expected to detect it via a new helper,
 * `filterGroupAsksForRecType` (`lib/planLineFilters.ts`, also not yet built - see its own
 * dedicated unit test file). Both are red today: the callback captured off the mocked
 * grid's props is `undefined`, so invoking it is a no-op and the grid keeps the DEFAULT
 * (hidden-respecting) list regardless of what group is "applied".
 */
describe('PlanLinesSection.visibleLines - a Filters condition reveals the hidden rows (AC-5b)', () => {
  function threeLineFixture() {
    const hidden = line({
      id: 'a', sku: 'HIDDEN-1', type: 'covered', policy_type: 'reorder_level',
      reorder_level: 50, net_position: 999, hidden_by_default: true,
    });
    const shownBuy = line({ id: 'b', sku: 'SHOWN-A', type: 'buy' });
    const shownCovered = line({
      id: 'c', sku: 'SHOWN-B', type: 'covered', policy_type: 'reorder_level',
      reorder_level: 50, net_position: 10, hidden_by_default: false,
    });
    return { hidden, shownBuy, shownCovered, lines: [hidden, shownBuy, shownCovered] };
  }

  const EQUALS_GROUP: ListQueryFilterGroup = {
    op: 'and',
    children: [{ field_key: 'rec_type', op: 'eq', value: 'covered_by_stock' }],
  };

  // Nested one group deep (AND wrapping an OR), operator `in` over a single-value list -
  // both variations the brief calls out in one condition.
  const NESTED_IN_GROUP: ListQueryFilterGroup = {
    op: 'and',
    children: [
      {
        op: 'or',
        children: [{ field_key: 'rec_type', op: 'in', value: ['covered_by_stock'] }],
      },
    ],
  };

  it('a top-level "Rec type equals Covered by stock" condition reveals all 3 of 3, and clearing it hides the 1 hidden row again (2 of 3)', () => {
    const { lines } = threeLineFixture();
    stubPlanLines({ lines });
    render(<PlanLinesSection runId="run-1" />);

    expect(gridSkus()).toHaveLength(2); // default: HIDDEN-1 excluded

    act(() => {
      latestOnFilterGroupChange?.(EQUALS_GROUP);
    });
    expect(gridSkus()).toHaveLength(3);
    expect(gridSkus()).toContain('HIDDEN-1');

    act(() => {
      latestOnFilterGroupChange?.(null);
    });
    expect(gridSkus()).toHaveLength(2);
    expect(gridSkus()).not.toContain('HIDDEN-1');
  });

  it('the same condition nested one group deep, operator "in" over [covered_by_stock], also reveals 3 of 3', () => {
    const { lines } = threeLineFixture();
    stubPlanLines({ lines });
    render(<PlanLinesSection runId="run-1" />);

    act(() => {
      latestOnFilterGroupChange?.(NESTED_IN_GROUP);
    });
    expect(gridSkus()).toHaveLength(3);
    expect(gridSkus()).toContain('HIDDEN-1');
  });

  it('the tile totals stay on the DEFAULT list while the reveal filter is applied - a lens, not a scope change', () => {
    const { lines } = threeLineFixture();
    stubPlanLines({ lines, decidedCount: 4, totalDecidableCount: 9 });
    const onTotalsChange = vi.fn();
    const onDecisionProgressChange = vi.fn();
    render(
      <PlanLinesSection
        runId="run-1"
        onTotalsChange={onTotalsChange}
        onDecisionProgressChange={onDecisionProgressChange}
      />,
    );

    onTotalsChange.mockClear();
    act(() => {
      latestOnFilterGroupChange?.(EQUALS_GROUP);
    });

    // The grid now sees all 3, but the cash/decision totals must still be counted over
    // the 2 the buyer would see by default - HIDDEN-1 must not inflate "undecided".
    expect(gridSkus()).toHaveLength(3);
    expect(onTotalsChange).toHaveBeenCalledWith(
      expect.objectContaining({ decided: 0, undecided: 2 }),
    );
    // The server-owned "N of Total made" header is untouched either way - it never read
    // `visibleLines` in the first place.
    expect(onDecisionProgressChange).toHaveBeenCalledWith({ decided: 4, total: 9 });
  });
});
