/**
 * PlanLinesSection - the extracted "one list" block (grid + budget review + level
 * changes) driven by usePlanLines. Both ReorderPlanningView and the SCM simulation
 * page's Planning view tab render this SAME component; this file checks the
 * orchestration (loading / error / data) in isolation from the heavy children.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import type { PlanLine } from '../lib/planLine';
import { recToPlanLine } from '../lib/planLine';
import type { ReorderRecommendation } from '../types/reorder.types';
import type { ToolbarAction } from '@/components/ui/data-grid-list-toolbar';

const usePlanLines = vi.fn();
vi.mock('../hooks/usePlanLines', () => ({ usePlanLines: (...a: unknown[]) => usePlanLines(...a) }));

vi.mock('./PlanLinesGrid', () => ({
  PlanLinesGrid: ({
    runId,
    statusFilter,
    decidedFilter,
    lines,
    secondaryActions,
  }: {
    runId: string | null;
    statusFilter: string | null;
    decidedFilter?: string;
    lines: PlanLine[];
    secondaryActions?: ToolbarAction[];
  }) => (
    <div>
      plan-lines-grid runId={runId} statusFilter={String(statusFilter)}
      decidedFilter={String(decidedFilter)}
      lines={lines.map((l) => l.sku).join(',')}
      secondaryActions={(secondaryActions ?? []).map((a) => a.key).join(',')}
    </div>
  ),
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

beforeEach(() => {
  usePlanLines.mockReset();
});

describe('PlanLinesSection - loading / error / data', () => {
  it('renders a skeleton while the plan lines are loading', () => {
    stubPlanLines({ isLoading: true });
    render(<PlanLinesSection runId="run-1" />);

    expect(screen.queryByText(/plan-lines-grid/)).not.toBeInTheDocument();
    expect(screen.queryByText('budget-review')).not.toBeInTheDocument();
  });

  it('renders an error card with retry when the plan lines fail to load', () => {
    const refetch = vi.fn();
    stubPlanLines({ isError: true, error: new Error('boom'), refetch });
    render(<PlanLinesSection runId="run-1" />);

    expect(screen.getByText('boom')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Try again/i }));
    expect(refetch).toHaveBeenCalled();
  });

  it('renders the grid, the budget review and the level changes panel once data is ready', () => {
    stubPlanLines();
    render(<PlanLinesSection runId="run-1" />);

    expect(screen.getByText(/plan-lines-grid/)).toBeInTheDocument();
    expect(screen.getByText('budget-review')).toBeInTheDocument();
    expect(screen.getByText('level-changes')).toBeInTheDocument();
  });

  it('passes the runId through to usePlanLines and the grid', () => {
    stubPlanLines();
    render(<PlanLinesSection runId="run-42" />);

    expect(usePlanLines).toHaveBeenCalledWith('run-42', true);
    expect(screen.getByText(/runId=run-42/)).toBeInTheDocument();
  });

  it('is disabled (does not enable the fetch) when there is no run yet', () => {
    stubPlanLines();
    render(<PlanLinesSection runId={null} />);

    expect(usePlanLines).toHaveBeenCalledWith(null, false);
  });

  it('forwards secondaryActions to the grid untouched, so a caller can wire in the ' +
    'Order summary / Plan exceptions / PO worklist links the removed tiles used to open', () => {
    stubPlanLines();
    const secondaryActions: ToolbarAction[] = [
      { key: 'order_summary', label: 'Order summary', onClick: vi.fn() },
    ];
    render(<PlanLinesSection runId="run-1" secondaryActions={secondaryActions} />);

    expect(screen.getByText(/secondaryActions=order_summary/)).toBeInTheDocument();
  });

  it('passes nothing through when the caller supplies no secondaryActions', () => {
    stubPlanLines();
    render(<PlanLinesSection runId="run-1" />);

    expect(screen.getByText(/plan-lines-grid/).textContent).toContain('secondaryActions=');
    expect(screen.getByText(/plan-lines-grid/).textContent).not.toContain('order_summary');
  });
});

describe('PlanLinesSection - status filter', () => {
  it('owns its own filter state when uncontrolled', () => {
    stubPlanLines();
    render(<PlanLinesSection runId="run-1" />);

    expect(screen.getByText(/statusFilter=null/)).toBeInTheDocument();
  });

  it('honours a controlled statusFilter from the caller', () => {
    stubPlanLines();
    render(
      <PlanLinesSection runId="run-1" statusFilter="needs_level" onStatusFilterChange={vi.fn()} />,
    );

    expect(screen.getByText(/statusFilter=needs_level/)).toBeInTheDocument();
  });
});

describe('PlanLinesSection - decided filter (the decision-progress tile drives this)', () => {
  it('owns its own decided filter state when uncontrolled', () => {
    stubPlanLines();
    render(<PlanLinesSection runId="run-1" />);

    expect(screen.getByText(/decidedFilter=all/)).toBeInTheDocument();
  });

  it('honours a controlled decidedFilter from the caller', () => {
    stubPlanLines();
    render(
      <PlanLinesSection runId="run-1" decidedFilter="undecided" onDecidedFilterChange={vi.fn()} />,
    );

    expect(screen.getByText(/decidedFilter=undecided/)).toBeInTheDocument();
  });
});

describe('PlanLinesSection - reports totals upward for the decision-progress tile', () => {
  it('calls onTotalsChange with the totals rolled up from the rendered lines', () => {
    const decided = line({ id: 'a', sku: 'BUY-1', type: 'buy' });
    const undecided = line({ id: 'b', sku: 'BUY-2', type: 'buy' });
    const decisions = { a: { buy: 23 } };
    stubPlanLines({ lines: [decided, undecided], decisions });
    const onTotalsChange = vi.fn();
    render(<PlanLinesSection runId="run-1" onTotalsChange={onTotalsChange} />);

    expect(onTotalsChange).toHaveBeenCalledWith(
      expect.objectContaining({ decided: 1, undecided: 1, buying: 1, units: 23 }),
    );
  });

  it('never calls onTotalsChange when the caller does not pass it', () => {
    stubPlanLines();
    expect(() => render(<PlanLinesSection runId="run-1" />)).not.toThrow();
  });

  it('does NOT count a row hidden by the default manual-mode filter (Fix 1, 2026-08-12): ' +
    'a not-breached covered row stays out of the tile the same way it stays out of the grid', () => {
    const visibleBuy = line({ id: 'a', sku: 'BUY-1', type: 'buy' });
    const hiddenCovered = line({
      id: 'b', sku: 'COV-NOT-BREACHED', type: 'covered',
      policy_type: 'reorder_level', reorder_level: 120, net_position: 135,
    });
    stubPlanLines({ lines: [visibleBuy, hiddenCovered], decisions: {} });
    const onTotalsChange = vi.fn();
    render(<PlanLinesSection runId="run-1" onTotalsChange={onTotalsChange} />);

    // Only the visible buy row counts: 1 undecided, not 2 - the hidden row is invisible
    // under the grid's own filter and must not inflate "N left" either.
    expect(onTotalsChange).toHaveBeenCalledWith(
      expect.objectContaining({ decided: 0, undecided: 1 }),
    );
  });

  it('DOES count the hidden row once the "covered by stock" status filter reveals it', () => {
    const visibleBuy = line({ id: 'a', sku: 'BUY-1', type: 'buy' });
    const revealedCovered = line({
      id: 'b', sku: 'COV-NOT-BREACHED', type: 'covered',
      policy_type: 'reorder_level', reorder_level: 120, net_position: 135,
    });
    stubPlanLines({ lines: [visibleBuy, revealedCovered], decisions: {} });
    const onTotalsChange = vi.fn();
    render(
      <PlanLinesSection
        runId="run-1"
        statusFilter="covered_by_stock"
        onStatusFilterChange={vi.fn()}
        onTotalsChange={onTotalsChange}
      />,
    );

    expect(onTotalsChange).toHaveBeenCalledWith(
      expect.objectContaining({ decided: 0, undecided: 2 }),
    );
  });
});

describe('PlanLinesSection - manual mode hides not-breached covered rows by default (Fix B, user feedback, 2026-08-12)', () => {
  it('hides a not-breached covered row in manual mode', () => {
    const notBreached = line({
      id: 'a', sku: 'COV-NOT-BREACHED', type: 'covered',
      policy_type: 'reorder_level', reorder_level: 120, net_position: 135,
    });
    const breached = line({
      id: 'b', sku: 'COV-BREACHED', type: 'covered',
      policy_type: 'reorder_level', reorder_level: 120, net_position: 30,
    });
    stubPlanLines({ lines: [notBreached, breached] });
    render(<PlanLinesSection runId="run-1" />);

    const grid = screen.getByText(/plan-lines-grid/);
    expect(grid.textContent).not.toContain('COV-NOT-BREACHED');
    expect(grid.textContent).toContain('COV-BREACHED');
  });

  it('shows the not-breached row again when the status filter is explicitly "covered by stock"', () => {
    const notBreached = line({
      id: 'a', sku: 'COV-NOT-BREACHED', type: 'covered',
      policy_type: 'reorder_level', reorder_level: 120, net_position: 135,
    });
    stubPlanLines({ lines: [notBreached] });
    render(<PlanLinesSection runId="run-1" statusFilter="covered_by_stock" onStatusFilterChange={vi.fn()} />);

    expect(screen.getByText(/plan-lines-grid/).textContent).toContain('COV-NOT-BREACHED');
  });

  it('a breached covered row (real gap, pool-cover case) is always visible', () => {
    const breached = line({
      id: 'a', sku: 'COV-BREACHED', type: 'covered',
      policy_type: 'reorder_level', reorder_level: 120, net_position: 30,
    });
    stubPlanLines({ lines: [breached] });
    render(<PlanLinesSection runId="run-1" />);

    expect(screen.getByText(/plan-lines-grid/).textContent).toContain('COV-BREACHED');
  });

  it('auto-mode (reorder_point basis) rows are unaffected, breached or not', () => {
    const autoNotBreached = line({
      id: 'a', sku: 'AUTO-NOT-BREACHED', type: 'covered',
      policy_type: 'reorder_point', reorder_point: 74, net_position: 100,
    });
    stubPlanLines({ lines: [autoNotBreached] });
    render(<PlanLinesSection runId="run-1" />);

    expect(screen.getByText(/plan-lines-grid/).textContent).toContain('AUTO-NOT-BREACHED');
  });

  it('a manual-basis buy row (not covered) is unaffected', () => {
    const buyRow = line({
      id: 'a', sku: 'MANUAL-BUY', type: 'buy',
      policy_type: 'reorder_level', reorder_level: 120, net_position: 100,
    });
    stubPlanLines({ lines: [buyRow] });
    render(<PlanLinesSection runId="run-1" />);

    expect(screen.getByText(/plan-lines-grid/).textContent).toContain('MANUAL-BUY');
  });
});
