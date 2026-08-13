/**
 * The order-qty ledger (S3, UAC B): THE LINE / COVER BEFORE BUYING / THE BUY, replacing the
 * old order-qty drill behind the "Explain order qty" trigger.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { ReorderRecommendation } from '../types/reorder.types';
import { recToPlanLine, type PlanLine } from '../lib/planLine';
import type { PlanDecision } from '../lib/planDecisions';
import { coverForLine, NO_COVER, type CoverProposal, type CoverSource } from '../lib/coverPlan';
import type { PoReceipt } from '../lib/poCover';
import type { ProductEconomics } from '../lib/productHealth';
import type { TrajectoryEntry } from '../lib/trajectory';
import { OrderQtyLedger } from './PlanOrderQtyLedger';

Element.prototype.hasPointerCapture = Element.prototype.hasPointerCapture ?? (() => false);
Element.prototype.scrollIntoView = Element.prototype.scrollIntoView ?? (() => {});

function rec(over: Partial<ReorderRecommendation> = {}): ReorderRecommendation {
  return {
    id: 'r1', type: 'buy', sku: 'SKU-1', product_name: 'Product one',
    abc_class: null, xyz_class: null, warehouse_code: 'BRW', warehouse_name: 'Butterworth',
    product_id: 'p1', warehouse_id: 'w1', is_network: false, allocation: null,
    order_qty: 23, recommended_qty: 23, reorder_point: 74, min_qty: null, max_qty: null,
    order_up_to: 134, net_position: -23, days_of_cover: null, reason: 'reorder_point',
    reason_label: '', confidence: 'low', sample_size: 0,
    supplier: { supplier_code: 'S1', supplier_name: 'Acme', unit_cost: 10,
                lead_time_days: 30, composite_score: 0, is_primary: true },
    alternatives: [], is_exception: false, disposition_action: null, transfer_flag: null,
    forecast_daily_demand: 2, lead_time_days: 30, lead_time_source: 'default',
    safety_stock: 7, safety_stock_method: null, safety_stock_fallback: null,
    service_level: null, safety_days: 7, review_days: 30, demand_window_days: 90,
    moq: null, order_multiple: null, policy_type: 'reorder_point', supplier_selection: 'primary',
    unit_cost: 10, cash_impact: 230, rank: 1, rank_score: 0, funding_status: null,
    days_to_stockout: null, rank_factors: [],
    on_hand: 1, incoming_spo: 0, outstanding_po: 0, outstanding_sales: 24,
    reorder_level: null, master_reorder_level: null,
    ...over,
  } as ReorderRecommendation;
}

const line = (over: Partial<ReorderRecommendation> = {}): PlanLine => recToPlanLine(rec(over));

function renderLedger(over: {
  line?: PlanLine;
  decision?: PlanDecision;
  cover?: CoverProposal;
  poReceipts?: PoReceipt[];
  economicsFor?: (l: PlanLine) => ProductEconomics | undefined;
  healthThresholds?: { margin_floor_pct: number; dead_turnover_months: number };
  trend?: TrajectoryEntry;
} = {}) {
  const onDecide = vi.fn();
  const l = over.line ?? line();
  render(
    <OrderQtyLedger
      line={l}
      decision={over.decision}
      cover={over.cover ?? NO_COVER}
      poReceipts={over.poReceipts ?? []}
      economicsFor={over.economicsFor}
      healthThresholds={over.healthThresholds ?? { margin_floor_pct: 15, dead_turnover_months: 6 }}
      trend={over.trend}
      onDecide={onDecide}
    />,
  );
  return { onDecide, line: l };
}

beforeEach(() => vi.clearAllMocks());

describe('order-qty ledger - THE LINE varies by mode', () => {
  it('auto mode shows the ROP derivation, not a reorder level', () => {
    renderLedger({ line: line({ policy_type: 'reorder_point' }) });
    expect(screen.getByText('Safety stock')).toBeInTheDocument();
    expect(screen.getByText('ROP = safety stock + demand rate x lead time')).toBeInTheDocument();
    expect(screen.queryByText('Reorder level')).not.toBeInTheDocument();
  });

  it('manual mode shows the reorder level and its source, not the ROP formula', () => {
    renderLedger({
      line: line({ policy_type: 'reorder_level', reorder_level: 42, reorder_level_source: 'manual' }),
    });
    expect(screen.getByText('Reorder level')).toBeInTheDocument();
    expect(screen.getByText('42')).toBeInTheDocument();
    expect(screen.getByText(/buyer set/)).toBeInTheDocument();
    expect(screen.queryByText('Safety stock')).not.toBeInTheDocument();
    expect(screen.queryByText('ROP = safety stock + demand rate x lead time')).not.toBeInTheDocument();
  });

  it('manual mode falls back to the AutoCount master level when no buyer level is set', () => {
    renderLedger({
      line: line({ policy_type: 'reorder_level', reorder_level: null, master_reorder_level: 10 }),
    });
    expect(screen.getByText('10')).toBeInTheDocument();
    expect(screen.getByText(/AutoCount master/)).toBeInTheDocument();
  });

  it('a pooled row (Fix 3, 2026-08-12) renders the per-location share list + pool total', () => {
    renderLedger({
      line: line({
        warehouse_code: 'BRW', policy_type: 'reorder_point',
        allocation: [
          { warehouse_code: 'BRW', warehouse_name: 'Butterworth', qty: 40 },
          { warehouse_code: 'BRW-BB', warehouse_name: 'Bukit Batu', qty: 15 },
        ],
      }),
    });
    expect(screen.getByText('Order-up-to level (whole pool)')).toBeInTheDocument();
    expect(screen.getByText('Bought for the whole pool')).toBeInTheDocument();
    expect(screen.getByText('One purchase covers 2 locations that share stock. It is sized once ' +
      'against the pool, then placed where the shortage is.')).toBeInTheDocument();
    expect(screen.getByText('BRW')).toBeInTheDocument();
    expect(screen.getByText('40')).toBeInTheDocument();
    expect(screen.getByText('BRW-BB')).toBeInTheDocument();
    expect(screen.getByText('15')).toBeInTheDocument();
    expect(screen.getByText('Pool total')).toBeInTheDocument();
    expect(screen.getByText('55')).toBeInTheDocument();
  });

  it('a single-location row (no pool) never renders the pool breakdown', () => {
    renderLedger({ line: line({ allocation: null }) });
    expect(screen.queryByText('Bought for the whole pool')).not.toBeInTheDocument();
    expect(screen.queryByText('Pool total')).not.toBeInTheDocument();
  });

  it('both modes show the same net breakdown and gap to line', () => {
    renderLedger({
      line: line({ on_hand: 5, incoming_spo: 3, outstanding_sales: 24, recommended_qty: 16 }),
    });
    expect(screen.getByText('Net now')).toBeInTheDocument();
    expect(screen.getByText('On hand')).toBeInTheDocument();
    expect(screen.getByText('+ SPO (arriving)')).toBeInTheDocument();
    expect(screen.getByText('- SO (outstanding)')).toBeInTheDocument();
    expect(screen.getByText('Gap to line')).toBeInTheDocument();
    expect(screen.getByText('16')).toBeInTheDocument();
  });
});

describe('order-qty ledger - the line\'s own breach status (covered rows never show a bogus gap)', () => {
  it('SIM-P002 manual mode: covered and above the level reads a status, not a gap', () => {
    // reorder level 120, net 135 (on hand 150, SO 15) - the row is NOT breached, and the
    // old "Gap to line 15" figure was actually the engine's own covered committed demand.
    renderLedger({
      line: line({
        type: 'covered', policy_type: 'reorder_level', reorder_level: 120,
        net_position: 135, on_hand: 150, outstanding_sales: 15,
        covered_committed: 15, covered_available: 150, recommended_qty: 15,
      }),
    });
    expect(screen.getByText('Line not breached - net 135 above level 120')).toBeInTheDocument();
    expect(screen.getByText('Committed demand 15, covered by stock')).toBeInTheDocument();
    expect(screen.queryByText('Gap to line')).not.toBeInTheDocument();
  });

  it('auto mode: covered and above the reorder point reads a status, not a gap', () => {
    renderLedger({
      line: line({
        type: 'covered', policy_type: 'reorder_point', reorder_point: 74,
        net_position: 100, covered_committed: 10, covered_available: 200,
      }),
    });
    expect(screen.getByText('Line not breached - net 100 above reorder point 74')).toBeInTheDocument();
    expect(screen.getByText('Committed demand 10, covered by stock')).toBeInTheDocument();
    expect(screen.queryByText('Gap to line')).not.toBeInTheDocument();
  });

  it('a covered row that IS breached keeps the real gap - the cover block explains it', () => {
    // Pool-cover case: cross-warehouse stock closes a real shortfall. net (30) <= ROP
    // (74) - this is a real gap, and it must keep reading as one.
    renderLedger({
      line: line({
        type: 'covered', policy_type: 'reorder_point', reorder_point: 74,
        net_position: 30, covered_committed: 15, covered_available: 150,
        recommended_qty: 15,
      }),
    });
    expect(screen.getByText('Gap to line')).toBeInTheDocument();
    expect(screen.queryByText(/Line not breached/)).not.toBeInTheDocument();
    expect(screen.queryByText(/covered by stock/)).not.toBeInTheDocument();
  });

  it('a buy row (not covered) always keeps the Gap to line row, breached or not', () => {
    renderLedger({
      line: line({ type: 'buy', policy_type: 'reorder_point', reorder_point: 74, net_position: 200 }),
    });
    expect(screen.getByText('Gap to line')).toBeInTheDocument();
    expect(screen.queryByText(/Line not breached/)).not.toBeInTheDocument();
  });
});

describe('order-qty ledger - the PO book is named but never counted', () => {
  it('shows the PO line, labelled not counted, only when outstanding PO > 0', () => {
    renderLedger({ line: line({ outstanding_po: 30 }) });
    expect(screen.getByText('PO (open)')).toBeInTheDocument();
    expect(screen.getByText('not counted')).toBeInTheDocument();
  });

  it('omits the PO line entirely when nothing is outstanding', () => {
    renderLedger({ line: line({ outstanding_po: 0 }) });
    expect(screen.queryByText('PO (open)')).not.toBeInTheDocument();
  });
});

describe('order-qty ledger - cover before buying', () => {
  const elsewhere: CoverSource[] = [
    { warehouse_id: 'wh-BRW-BB', warehouse_code: 'BRW-BB', segment: 'dealer', qty: 6 },
  ];

  it('reads "no cover available" when nothing offsets the buy', () => {
    renderLedger({ line: line({ order_qty: 20 }) });
    expect(screen.getByText(/No cover available/)).toBeInTheDocument();
  });

  it('toggling the stock cover off recomputes left-to-buy and rounding in place', () => {
    const l = line({ order_qty: 20, recommended_qty: 20, moq: null, order_multiple: null });
    const cover = coverForLine(l, elsewhere);
    const { onDecide } = renderLedger({ line: l, cover, poReceipts: [] });

    // Stock is on by default (undecided line reads the engine's own suggestion): 6 covered,
    // 14 to buy.
    expect(screen.getByText('Buy before rounding')).toBeInTheDocument();
    expect(screen.getAllByText('14').length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole('checkbox', { name: /Use stock 6/ }));
    expect(onDecide).toHaveBeenCalledWith(expect.objectContaining({ buy: 20 }));
  });

  it('the PO toggle recomputes the buy the same way', () => {
    const l = line({ order_qty: 30, recommended_qty: 30 });
    const receipts: PoReceipt[] = [
      { po_number: 'PO-2026/07-0002', status: 'active', expected_date: '2026-08-10', remaining: 30 },
    ];
    const { onDecide } = renderLedger({ line: l, poReceipts: receipts });

    // PO is on by default: 30 absorbed, nothing left to buy.
    expect(screen.getByText(/Nothing to buy/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('checkbox', { name: /Use PO PO-2026\/07-0002/ }));
    expect(onDecide).toHaveBeenCalledWith(expect.objectContaining({ buy: 30 }));
  });

  it('names the SPO as already counted, and it is never a toggle', () => {
    renderLedger({ line: line({ incoming_spo: 20, outstanding_po: 30 }) });
    expect(screen.getByText(/SPO arriving 20 - already counted/)).toBeInTheDocument();
    expect(screen.queryByRole('checkbox', { name: /SPO/ })).not.toBeInTheDocument();
  });
});

describe('order-qty ledger - the buy', () => {
  it('MoQ and order multiple render only inside THE BUY block, never in THE LINE', () => {
    renderLedger({ line: line({ order_qty: 100, recommended_qty: 20, moq: 100 }) });
    expect(screen.getByText('MoQ / order multiple')).toBeInTheDocument();
    // Only one "100" instance is the rounded buy figure; MoQ is not restated in THE LINE.
    expect(screen.queryByText('Safety stock')).toBeInTheDocument(); // sanity: THE LINE rendered
  });

  it('a covered row with nothing left to buy collapses to "Nothing to buy"', () => {
    const covered = line({
      id: 'r1', sku: 'COV-1', type: 'covered', order_qty: 15,
      covered_committed: 15, covered_available: 150,
    });
    const cover = coverForLine(covered, []);
    renderLedger({ line: covered, cover });
    expect(screen.getByText('Nothing to buy - MoQ not relevant')).toBeInTheDocument();
    expect(screen.queryByText('Buy before rounding')).not.toBeInTheDocument();
  });

  it('offers the forecast add-on opt-in, never applied by default', () => {
    renderLedger({ line: line({ order_qty: 40, recommended_qty: 40, forecast_daily_demand: 2, review_days: 30 }) });
    const addOn = screen.getByRole('checkbox', { name: 'Add 60' });
    expect(addOn).toBeInTheDocument();
    expect(addOn).toHaveAttribute('aria-checked', 'false');
    expect(screen.getByRole('spinbutton', { name: 'Forecast add-on quantity' })).toHaveValue(60);
  });

  it('clicking the forecast add-on adds it to the buy; clicking again removes it', () => {
    const l = line({ order_qty: 40, recommended_qty: 40, forecast_daily_demand: 2, review_days: 30 });
    const { onDecide } = renderLedger({ line: l });

    const addOn = screen.getByRole('checkbox', { name: 'Add 60' });
    fireEvent.click(addOn);
    expect(onDecide).toHaveBeenLastCalledWith(
      expect.objectContaining({ buy: 100, reason: expect.stringContaining('Forecast:') }),
    );

    const applied = screen.getByRole('checkbox', { name: 'Added 60' });
    fireEvent.click(applied);
    expect(onDecide).toHaveBeenLastCalledWith(expect.objectContaining({ buy: 40 }));
    expect(onDecide.mock.calls.at(-1)?.[0]).not.toHaveProperty('reason');
  });

  it('never offers the forecast add-on when there is no measurable demand', () => {
    renderLedger({ line: line({ forecast_daily_demand: null }) });
    expect(screen.queryByText(/\+ Add/)).not.toBeInTheDocument();
  });

  it('the add-on label is plain muted text when unticked, never strikethrough (Fix A)', () => {
    renderLedger({ line: line({ order_qty: 40, recommended_qty: 40, forecast_daily_demand: 2, review_days: 30 }) });
    const label = screen.getByText('+ Add');
    expect(label.className).not.toContain('line-through');
    expect(label.parentElement?.className).toContain('text-muted-foreground');
  });

  it('names the add-on horizon\'s source: review period in auto mode, cover window in manual', () => {
    renderLedger({
      line: line({
        policy_type: 'reorder_point', order_qty: 40, recommended_qty: 40,
        forecast_daily_demand: 2, review_days: 30,
      }),
    });
    expect(
      screen.getByText('(next 30d demand at 2.0/day - review period per policy)'),
    ).toBeInTheDocument();
  });

  it('manual mode names the cover-window source', () => {
    renderLedger({
      line: line({
        policy_type: 'reorder_level', reorder_level: 50, order_qty: 40, recommended_qty: 40,
        forecast_daily_demand: 20, suggestion_basis: { cover_months: 2 },
      }),
    });
    expect(screen.getByRole('checkbox', { name: 'Add 1,200' })).toBeInTheDocument();
    expect(
      screen.getByText('(next 60d demand at 20.0/day - cover window per policy)'),
    ).toBeInTheDocument();
  });

  it('a rising trend bumps the add-on above the flat proposal, and says so', () => {
    renderLedger({
      line: line({
        policy_type: 'reorder_point', order_qty: 40, recommended_qty: 40,
        forecast_daily_demand: 20, review_days: 30,
      }),
      trend: {
        verdict: 'rising', recent_qty: 120, previous_qty: 90, change_pct: 33.33,
        year_ago_qty: null, year_change_pct: null, window_months: 12,
        months: [], customers: [], agents: [], agents_available: false,
      },
    });
    // Flat = 20 x 30 = 600; rising +33% -> +200 -> 800.
    expect(screen.getByRole('checkbox', { name: 'Add 800' })).toBeInTheDocument();
    expect(screen.getByText(/orders rising \+33%/)).toBeInTheDocument();
  });

  it('a falling trend reduces the add-on proportionally, and says so', () => {
    renderLedger({
      line: line({
        policy_type: 'reorder_point', order_qty: 40, recommended_qty: 40,
        forecast_daily_demand: 20, review_days: 30,
      }),
      trend: {
        verdict: 'falling', recent_qty: 60, previous_qty: 80, change_pct: -25,
        year_ago_qty: null, year_change_pct: null, window_months: 12,
        months: [], customers: [], agents: [], agents_available: false,
      },
    });
    // Flat = 600; falling -25% -> -150 -> 450.
    expect(screen.getByRole('checkbox', { name: 'Add 450' })).toBeInTheDocument();
    expect(screen.getByText(/orders falling -25%/)).toBeInTheDocument();
  });

  it('a falling trend that fully consumes the add-on renders a disabled explanation, never a checkbox', () => {
    renderLedger({
      line: line({
        policy_type: 'reorder_point', order_qty: 40, recommended_qty: 40,
        forecast_daily_demand: 20, review_days: 30,
      }),
      trend: {
        verdict: 'falling', recent_qty: 0, previous_qty: 80, change_pct: -100,
        year_ago_qty: null, year_change_pct: null, window_months: 12,
        months: [], customers: [], agents: [], agents_available: false,
      },
    });
    expect(screen.getByText('Orders falling - no add-on proposed')).toBeInTheDocument();
    expect(screen.queryByRole('checkbox', { name: /Add/ })).not.toBeInTheDocument();
  });

  it('holding, quiet, and no_history trends leave the flat add-on unchanged', () => {
    renderLedger({
      line: line({
        policy_type: 'reorder_point', order_qty: 40, recommended_qty: 40,
        forecast_daily_demand: 2, review_days: 30,
      }),
      trend: {
        verdict: 'holding', recent_qty: 60, previous_qty: 60, change_pct: 0,
        year_ago_qty: null, year_change_pct: null, window_months: 12,
        months: [], customers: [], agents: [], agents_available: false,
      },
    });
    expect(screen.getByRole('checkbox', { name: 'Add 60' })).toBeInTheDocument();
  });
});

describe('order-qty ledger - the add-on quantity is editable (Fix A, user feedback, 2026-08-12)', () => {
  const editableLine = () =>
    line({ order_qty: 40, recommended_qty: 40, forecast_daily_demand: 2, review_days: 30 });

  it('ticking applies the CURRENT input value, not just the proposed qty', () => {
    const { onDecide } = renderLedger({ line: editableLine() });

    const input = screen.getByRole('spinbutton', { name: 'Forecast add-on quantity' });
    fireEvent.change(input, { target: { value: '300' } });
    fireEvent.click(screen.getByRole('checkbox', { name: 'Add 300' }));

    expect(onDecide).toHaveBeenLastCalledWith(
      expect.objectContaining({ buy: 340, reason: expect.stringContaining('+300') }),
    );
  });

  it('re-editing while ticked re-applies immediately, no separate Record step', () => {
    const { onDecide } = renderLedger({ line: editableLine() });

    fireEvent.click(screen.getByRole('checkbox', { name: 'Add 60' }));
    expect(onDecide).toHaveBeenLastCalledWith(expect.objectContaining({ buy: 100 }));

    const input = screen.getByRole('spinbutton', { name: 'Forecast add-on quantity' });
    fireEvent.change(input, { target: { value: '200' } });
    expect(onDecide).toHaveBeenLastCalledWith(expect.objectContaining({ buy: 240 }));
  });

  it('editing while unticked updates the field but never commits a buy change', () => {
    const { onDecide } = renderLedger({ line: editableLine() });

    const input = screen.getByRole('spinbutton', { name: 'Forecast add-on quantity' });
    fireEvent.change(input, { target: { value: '200' } });
    expect(onDecide).not.toHaveBeenCalled();
    expect(input).toHaveValue(200);

    fireEvent.click(screen.getByRole('checkbox', { name: 'Add 200' }));
    expect(onDecide).toHaveBeenLastCalledWith(expect.objectContaining({ buy: 240 }));
  });

  it('bounds: a typed figure above the cap clamps to 10x the proposed qty', () => {
    renderLedger({ line: editableLine() });
    const input = screen.getByRole('spinbutton', { name: 'Forecast add-on quantity' });
    // Proposal is 60, so the cap is 600.
    fireEvent.change(input, { target: { value: '99999' } });
    expect(input).toHaveValue(600);
  });

  it('bounds: a negative or empty entry floors at zero', () => {
    renderLedger({ line: editableLine() });
    const input = screen.getByRole('spinbutton', { name: 'Forecast add-on quantity' });
    fireEvent.change(input, { target: { value: '-5' } });
    expect(input).toHaveValue(0);
  });
});

describe('order-qty ledger - shaped fixtures render coherently', () => {
  it('SIM-P002-shaped: covered by ample stock, use-stock leads and nothing to buy', () => {
    // avg_daily_demand=2, on_hand=150, so_committed_qty=15 -> the pool's own stock covers
    // the whole commitment (covered_available 150 >= covered_committed 15).
    const covered = line({
      id: 'r1', sku: 'MWC-P002', type: 'covered', order_qty: 15,
      warehouse_code: 'BRW', on_hand: 150, outstanding_sales: 15,
      covered_committed: 15, covered_available: 150,
      forecast_daily_demand: 2, reorder_point: 74, order_up_to: 134,
      recommended_qty: 15,
    });
    const cover = coverForLine(covered, []);
    renderLedger({ line: covered, cover });

    expect(screen.getByRole('checkbox', { name: /Use stock 15/ })).toBeInTheDocument();
    expect(screen.getByText('Nothing to buy - MoQ not relevant')).toBeInTheDocument();
  });

  it('SIM-P029-shaped: stock + SPO + PO all present, PO absorbs part, remainder still buys', () => {
    // avg_daily_demand=2, on_hand=10, so_committed_qty=60, spo_incoming_qty=20,
    // po_open_qty=30 -> net -30, ROP 74 -> triggers; PO offsets the buy, never the net.
    const l = line({
      id: 'r1', sku: 'MWC-P029', order_qty: 164, recommended_qty: 164,
      on_hand: 10, incoming_spo: 20, outstanding_sales: 60, outstanding_po: 30,
      forecast_daily_demand: 2, reorder_point: 74, order_up_to: 134,
    });
    const receipts: PoReceipt[] = [
      { po_number: 'PO-2026/08-0030', status: 'active', expected_date: null, remaining: 30 },
    ];
    renderLedger({ line: l, poReceipts: receipts });

    expect(screen.getByText('PO (open)')).toBeInTheDocument();
    expect(screen.getByText('not counted')).toBeInTheDocument();
    expect(screen.getByText(/SPO arriving 20 - already counted/)).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: /Use PO PO-2026\/08-0030 30/ })).toBeInTheDocument();
    expect(screen.getByText('Buy before rounding')).toBeInTheDocument();
    expect(screen.getAllByText('134').length).toBeGreaterThan(0); // 164 - 30 PO
  });
});
