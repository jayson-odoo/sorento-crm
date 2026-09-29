/**
 * PlanLinesSection - the extracted "one list" block (grid + budget review + level
 * changes) driven by usePlanLines. Both the plan page and the SCM simulation
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

const toastSuccess = vi.fn();
const toastError = vi.fn();
const toastInfo = vi.fn();
vi.mock('@/lib/toast', () => ({ toast: { success: (...a: unknown[]) => toastSuccess(...a),
                                          error: (...a: unknown[]) => toastError(...a),
                                          info: (...a: unknown[]) => toastInfo(...a) } }));

const usePlanLines = vi.fn();
vi.mock('../hooks/usePlanLines', () => ({ usePlanLines: (...a: unknown[]) => usePlanLines(...a) }));

// The draft map has its own suite (`usePlanEdits` is exercised through `PlanLinesGrid`);
// here it would only drag a QueryClient into every case that is about orchestration.
// A `vi.fn()`, not a fixed object, so AC-S6.3's Confirm-tooltip test below can vary
// `confirmable.products` per case - the same shape `usePlanLines` already uses.
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

vi.mock('./PlanLinesGrid', () => ({
  PlanLinesGrid: ({
    runId,
    statusFilter,
    decidedFilter,
    lines,
    secondaryActions,
    toolbarPrimary,
    onSaveRow,
    savingFor,
  }: {
    runId: string | null;
    statusFilter: string | null;
    decidedFilter?: string;
    lines: PlanLine[];
    secondaryActions?: ToolbarAction[];
    toolbarPrimary?: React.ReactNode;
    onSaveRow?: (line: PlanLine) => void;
    savingFor?: (line: PlanLine) => boolean;
  }) => (
    <div>
      plan-lines-grid runId={runId} statusFilter={String(statusFilter)}
      decidedFilter={String(decidedFilter)}
      lines={lines.map((l) => l.sku).join(',')}
      secondaryActions={(secondaryActions ?? []).map((a) => a.key).join(',')}
      {/* AC-S12.1 (round 2, review fix): a stand-in for the panel's own row Save, so a
          test can reach the wrapper `PlanLinesSection` builds (`doSaveRow`) the same
          way it reaches the toolbar's through `toolbarPrimary` below. */}
      {lines[0] ? (
        <button
          disabled={savingFor?.(lines[0]) ?? false}
          onClick={() => onSaveRow?.(lines[0])}
        >
          {savingFor?.(lines[0]) ? 'row-saving' : 'row-save'}
        </button>
      ) : null}
      {/* AC-S6.3: the real grid renders Save/Confirm at the toolbar's right end
          (`toolbarPrimary`) - rendered here too so a test can reach the actual buttons
          `PlanLinesSection` builds, not a restated copy of them. */}
      {toolbarPrimary}
    </div>
  ),
}));
// The mock surfaces `totals` (as text, alongside the plain "budget-review" marker every
// existing case in this file already matches on) so AC-13 can assert WHICH totals object
// `PlanLinesSection` actually hands the review panel, without pulling in the real
// component (heavy children stay mocked, per this file's own stated purpose).
vi.mock('./PlanBudgetReview', () => ({
  PlanBudgetReview: ({ totals }: { totals: { decided: number; undecided: number } }) => (
    <div>
      <div>budget-review</div>
      <div>{`${totals.decided} of ${totals.decided + totals.undecided}`}</div>
      {totals.undecided > 0 ? (
        <div>{`${totals.undecided} line${totals.undecided === 1 ? '' : 's'} still to decide`}</div>
      ) : null}
    </div>
  ),
}));
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
    // S16: the server's own "N of Total made" - independent of `lines`/`decisions` above.
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

beforeEach(() => {
  usePlanLines.mockReset();
  usePlanEditsMock.mockReset();
  toastSuccess.mockReset();
  toastError.mockReset();
  toastInfo.mockReset();
  stubPlanEdits();
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

  it('PLAN-lowstock-show-all AC-70 (owner 30 Sep, reversing the 12 Aug rule): a covered ' +
    'row whose payload still says hidden_by_default:true counts toward the tile like any other', () => {
    const buy = line({ id: 'a', sku: 'BUY-1', type: 'buy' });
    const coveredAboveLevel = line({
      id: 'b', sku: 'COV-ABOVE-LEVEL', type: 'covered',
      policy_type: 'reorder_level', reorder_level: 120, net_position: 135,
      // An old run's payload still carries the retired flag; the list must not act on it.
      hidden_by_default: true,
    } as Partial<ReorderRecommendation>);
    stubPlanLines({ lines: [buy, coveredAboveLevel], decisions: {} });
    const onTotalsChange = vi.fn();
    render(<PlanLinesSection runId="run-1" onTotalsChange={onTotalsChange} />);

    expect(onTotalsChange).toHaveBeenCalledWith(
      expect.objectContaining({ decided: 0, undecided: 2 }),
    );
  });

  it('PLAN-lowstock-show-all AC-70: PlanBudgetReview reads the totals rolled up from EVERY ' +
    'line the hook returned - the same set the tile and the grid render', () => {
    // 3 lines, one stamped hidden_by_default by an old run. `planLines.totals` is stubbed
    // to a WRONG figure on purpose: the review panel must read `reportedTotals` (rolled
    // up from the rendered lines), never the hook's own stale object.
    const a = line({ id: 'a', sku: 'BUY-1', type: 'buy' });
    const b = line({ id: 'b', sku: 'BUY-2', type: 'buy' });
    const stamped = line({
      id: 'c', sku: 'COV-STAMPED', type: 'covered',
      policy_type: 'reorder_level', reorder_level: 120, net_position: 135,
      hidden_by_default: true,
    } as Partial<ReorderRecommendation>);
    stubPlanLines({
      lines: [a, b, stamped],
      decisions: {},
      totals: {
        decided: 0, undecided: 99, buying: 2, usingStock: 0, usingPo: 0, skipped: 0,
        units: 0, cost: 0, unpriced: 0,
      },
    });
    render(<PlanLinesSection runId="run-1" />);

    expect(screen.getByText('0 of 3')).toBeInTheDocument();
    expect(screen.getByText('3 lines still to decide')).toBeInTheDocument();
    expect(screen.queryByText('0 of 99')).not.toBeInTheDocument();
  });

  it('counts the per-warehouse rows even under a Product-grain run (S16, 21 Aug): a decision ' +
    'lives on the underlying member recommendation id, never a synthetic group key', () => {
    // 3 per-warehouse rows for 2 products - PlanLinesGrid itself renders this as 2 rows
    // when `groupByChannel` is on, but S16 fans a group decision out to its real member
    // ids (`usePlanLines.decide`, mirroring `updateMoq`), so this tile's own count stays
    // the real, decidable row count - never the grouped presentation count. Superseded
    // test (19-20 Aug): the old "Decided at Product grain" lock made a group row
    // genuinely undecidable, which is exactly what S16 removed.
    const p1a = line({ id: 'a', sku: 'SKU-1', product_id: 'p1', warehouse_id: 'w1' });
    const p1b = line({ id: 'b', sku: 'SKU-1', product_id: 'p1', warehouse_id: 'w2' });
    const p2a = line({ id: 'c', sku: 'SKU-2', product_id: 'p2', warehouse_id: 'w3' });
    const decisions = { a: { buy: 5 } }; // one member of the SKU-1 group has been decided
    stubPlanLines({ lines: [p1a, p1b, p2a], decisions });
    const onTotalsChange = vi.fn();
    render(<PlanLinesSection runId="run-1" groupByChannel onTotalsChange={onTotalsChange} />);

    expect(onTotalsChange).toHaveBeenCalledWith(
      expect.objectContaining({ decided: 1, undecided: 2 }),
    );
  });

  it('keeps the PER-WAREHOUSE count when the run is not Product-grain (groupByChannel unset)', () => {
    const p1a = line({ id: 'a', sku: 'SKU-1', product_id: 'p1', warehouse_id: 'w1' });
    const p1b = line({ id: 'b', sku: 'SKU-1', product_id: 'p1', warehouse_id: 'w2' });
    stubPlanLines({ lines: [p1a, p1b], decisions: {} });
    const onTotalsChange = vi.fn();
    render(<PlanLinesSection runId="run-1" onTotalsChange={onTotalsChange} />);

    expect(onTotalsChange).toHaveBeenCalledWith(
      expect.objectContaining({ decided: 0, undecided: 2 }),
    );
  });

});

describe('PlanLinesSection - S16 decision-progress header count is the SERVER\'s own', () => {
  it('reports usePlanLines\' decidedCount/totalDecidableCount straight through, not a client re-derivation', () => {
    stubPlanLines({ decidedCount: 4, totalDecidableCount: 9 });
    const onDecisionProgressChange = vi.fn();
    render(<PlanLinesSection runId="run-1" onDecisionProgressChange={onDecisionProgressChange} />);

    expect(onDecisionProgressChange).toHaveBeenCalledWith({ decided: 4, total: 9 });
  });

  it('never calls onDecisionProgressChange when the caller does not pass it', () => {
    stubPlanLines();
    expect(() => render(<PlanLinesSection runId="run-1" />)).not.toThrow();
  });
});

describe('PlanLinesSection - the list is the run: every line renders (PLAN-lowstock-show-all, owner 30 Sep 2026)', () => {
  // Reverses the 12 Aug "not my business" rule (Fix B) and its 10 Sep server-flag twin
  // (PLAN-plan-list-tile-sheet-one-scope S6): nothing is hidden by default any more, and
  // there is no reveal filter because there is nothing left to reveal.

  it('renders a covered row whose net sits above its manual level, with no filter applied', () => {
    const aboveLevel = line({
      id: 'a', sku: 'COV-ABOVE-LEVEL', type: 'covered',
      policy_type: 'reorder_level', reorder_level: 120, net_position: 135,
    });
    const belowLevel = line({
      id: 'b', sku: 'COV-BELOW-LEVEL', type: 'covered',
      policy_type: 'reorder_level', reorder_level: 120, net_position: 30,
    });
    stubPlanLines({ lines: [aboveLevel, belowLevel] });
    render(<PlanLinesSection runId="run-1" />);

    expect(screen.getByText(/plan-lines-grid/).textContent).toContain(
      'lines=COV-ABOVE-LEVEL,COV-BELOW-LEVEL',
    );
  });

  it('renders a line whose payload still carries hidden_by_default:true (an old run) - the flag is retired', () => {
    const stamped = line({
      id: 'a', sku: 'COV-STAMPED', product_id: 'p-stamped', type: 'covered',
      warehouse_id: null, warehouse_code: null, warehouse_name: null,
      policy_type: 'reorder_level', reorder_level: 120, net_position: 135,
      hidden_by_default: true,
    } as Partial<ReorderRecommendation>);
    const other = line({ id: 'b', sku: 'BUY-1', product_id: 'p-other', type: 'buy' });
    stubPlanLines({ lines: [stamped, other] });
    render(<PlanLinesSection runId="run-1" />);

    expect(screen.getByText(/plan-lines-grid/).textContent).toContain('lines=COV-STAMPED,BUY-1');
  });

  it('renders the product-grain covered row AND its per-warehouse disposition, in hook order', () => {
    const productRow = line({
      id: 'a', sku: 'SRTWT7408', product_id: 'p-srt', type: 'covered',
      warehouse_id: null, warehouse_code: null, warehouse_name: null,
      policy_type: 'reorder_level', reorder_level: 500, net_position: 5758,
    });
    const disposition = line({
      id: 'b', sku: 'SRTWT7408', product_id: 'p-srt', type: 'disposition',
      warehouse_id: 'w-brw', warehouse_code: 'BRW', policy_type: 'reorder_level',
    });
    stubPlanLines({ lines: [productRow, disposition] });
    render(<PlanLinesSection runId="run-1" />);

    expect(screen.getByText(/plan-lines-grid/).textContent).toContain(
      'lines=SRTWT7408,SRTWT7408',
    );
  });

  it('the "covered by stock" status filter changes nothing about which lines reach the grid ' +
    '(the grid applies its own filters; the section passes every line)', () => {
    const aboveLevel = line({
      id: 'a', sku: 'COV-ABOVE-LEVEL', type: 'covered',
      policy_type: 'reorder_level', reorder_level: 120, net_position: 135,
    });
    const buy = line({ id: 'b', sku: 'BUY-1', type: 'buy' });
    stubPlanLines({ lines: [aboveLevel, buy] });
    render(<PlanLinesSection runId="run-1" statusFilter="covered_by_stock" onStatusFilterChange={vi.fn()} />);

    expect(screen.getByText(/plan-lines-grid/).textContent).toContain('lines=COV-ABOVE-LEVEL,BUY-1');
  });
});

describe('PlanLinesSection - Confirm button tooltip (AC-S6.3)', () => {
  it('reads "Decide at least one row first" and is disabled at Confirm (0)', () => {
    stubPlanLines();
    stubPlanEdits({ confirmable: { products: 0, cash: 0, unpriced: 0 } });
    render(<PlanLinesSection runId="run-1" />);

    const confirmButton = screen.getByRole('button', { name: /Confirm \(0\)/ });
    expect(confirmButton).toBeDisabled();
    expect(confirmButton).toHaveAttribute('title', 'Decide at least one row first');
  });

  it('drops the "decide a row" hint once a product is confirmable', () => {
    stubPlanLines();
    stubPlanEdits({ confirmable: { products: 2, cash: 500, unpriced: 0 } });
    render(<PlanLinesSection runId="run-1" />);

    const confirmButton = screen.getByRole('button', { name: /Confirm \(2\)/ });
    expect(confirmButton).not.toBeDisabled();
    expect(confirmButton).toHaveAttribute(
      'title',
      'Save, then turn this plan into draft purchase orders',
    );
  });
});

describe('PlanLinesSection - row Save feedback (AC-S12.1, review fix round 2)', () => {
  it('a rejecting saveRow toasts the extracted error and never clears the draft', async () => {
    const saveRow = vi.fn().mockRejectedValue(new Error('Could not reach the server.'));
    stubPlanLines({ lines: [line()] });
    stubPlanEdits({ saveRow, edits: { r1: { moq: 5 } } });
    render(<PlanLinesSection runId="run-1" />);

    fireEvent.click(screen.getByRole('button', { name: 'row-save' }));

    await vi.waitFor(() => expect(toastError).toHaveBeenCalledWith('Could not reach the server.'));
    expect(toastSuccess).not.toHaveBeenCalled();
    // The hook owns clearing the draft on success only - a rejected save never reaches
    // that line, so nothing here asserts the draft was touched.
  });

  it('toasts "Row saved." on a successful save', async () => {
    const saveRow = vi.fn().mockResolvedValue({ saved_rows: 1, saved_products: 1 });
    stubPlanLines({ lines: [line()] });
    stubPlanEdits({ saveRow });
    render(<PlanLinesSection runId="run-1" />);

    fireEvent.click(screen.getByRole('button', { name: 'row-save' }));

    await vi.waitFor(() => expect(toastSuccess).toHaveBeenCalledWith('Row saved.'));
    expect(toastError).not.toHaveBeenCalled();
  });

  it('disables the row Save affordance while that row is in flight', () => {
    stubPlanLines({ lines: [line()] });
    stubPlanEdits({ savingRowIds: new Set(['r1']) });
    render(<PlanLinesSection runId="run-1" />);

    expect(screen.getByRole('button', { name: 'row-saving' })).toBeDisabled();
  });

  // AC-S12.5: a row with nothing drafted and no un-blurred value to flush - `saveRow`
  // resolves null rather than PUTting an empty save - says so instead of staying silent
  // as if the click never happened, and fires no request either way.
  it('a row with nothing to save toasts "Nothing to save on this row." and fires no request', async () => {
    const saveRow = vi.fn().mockResolvedValue(null);
    stubPlanLines({ lines: [line()] });
    stubPlanEdits({ saveRow });
    render(<PlanLinesSection runId="run-1" />);

    fireEvent.click(screen.getByRole('button', { name: 'row-save' }));

    await vi.waitFor(() => expect(toastInfo).toHaveBeenCalledWith('Nothing to save on this row.'));
    expect(saveRow).toHaveBeenCalledTimes(1);
    expect(toastSuccess).not.toHaveBeenCalled();
    expect(toastError).not.toHaveBeenCalled();
  });
});

describe('PlanLinesSection - Confirm dialog copy (finding 4, review fix round 3)', () => {
  it('states the G5 rule, not the retired R3 sweep sentence', () => {
    stubPlanLines();
    stubPlanEdits({ confirmable: { products: 2, cash: 500, unpriced: 0 } });
    render(<PlanLinesSection runId="run-1" />);

    fireEvent.click(screen.getByRole('button', { name: /Confirm \(2\)/ }));

    expect(
      screen.getByText(/Only rows you decided are bought; untouched and skipped rows are left out\./),
    ).toBeInTheDocument();
    expect(screen.queryByText(/confirmed as the plan suggested/)).not.toBeInTheDocument();
  });
});
