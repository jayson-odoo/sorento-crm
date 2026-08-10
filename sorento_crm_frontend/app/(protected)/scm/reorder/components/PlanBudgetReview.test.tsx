/**
 * The money question, asked after the decisions.
 *
 * The failure mode this guards is a total that looks finished when it is not: an unread plan
 * that sums to a small number, or a verdict of "within budget" reached over lines nobody could
 * price.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { ReorderRecommendation } from '../types/reorder.types';
import { recToPlanLine, type PlanLine } from '../lib/planLine';
import { planTotals, type PlanDecisionMap } from '../lib/planDecisions';
import { PlanBudgetReview } from './PlanBudgetReview';

function rec(over: Partial<ReorderRecommendation> = {}): ReorderRecommendation {
  return {
    id: 'r1', type: 'buy', sku: 'SKU-1', product_name: 'Product one',
    abc_class: null, xyz_class: null, warehouse_code: 'BRW', warehouse_name: 'Butterworth',
    product_id: 'p1', warehouse_id: 'w1', is_network: false, allocation: null,
    order_qty: 10, recommended_qty: 10, reorder_point: 0, min_qty: null, max_qty: null,
    order_up_to: 0, net_position: -10, days_of_cover: null, reason: 'reorder_point',
    reason_label: '', confidence: 'low', sample_size: 0,
    supplier: { supplier_code: 'S1', supplier_name: 'Acme', unit_cost: 10,
                lead_time_days: 30, composite_score: 0, is_primary: true },
    alternatives: [], is_exception: false, disposition_action: null, transfer_flag: null,
    forecast_daily_demand: 0, lead_time_days: 30, lead_time_source: 'default',
    safety_stock: 0, safety_stock_method: null, safety_stock_fallback: null,
    service_level: null, safety_days: 0, review_days: 0,
    moq: null, order_multiple: null, policy_type: 'reorder_point', supplier_selection: 'primary',
    unit_cost: 10, cash_impact: 100, rank: 1, rank_score: 0, funding_status: null,
    days_to_stockout: null, rank_factors: [],
    on_hand: 0, incoming_spo: 0, outstanding_po: 0, outstanding_sales: 10,
    ...over,
  } as ReorderRecommendation;
}

const line = (over: Partial<ReorderRecommendation> = {}): PlanLine => recToPlanLine(rec(over));

function renderReview(lines: PlanLine[], decisions: PlanDecisionMap) {
  render(
    <PlanBudgetReview
      lines={lines}
      decisions={decisions}
      totals={planTotals(lines, decisions)}
    />,
  );
}

beforeEach(() => vi.clearAllMocks());

describe('PlanBudgetReview - what has been decided', () => {
  it('says how much of the plan is still unread, so a part-total cannot pass as a whole one', () => {
    const lines = [line({ id: 'a' }), line({ id: 'b' }), line({ id: 'c' })];
    renderReview(lines, { a: { kind: 'buy' } } as PlanDecisionMap);
    expect(screen.getByText(/2 lines still to decide/i)).toBeInTheDocument();
  });

  it('gives no verdict at all until a budget is typed', () => {
    renderReview([line()], { r1: { kind: 'buy' } } as PlanDecisionMap);
    expect(screen.queryByText(/Within budget/i)).toBeNull();
    expect(screen.queryByText(/Over by/i)).toBeNull();
  });
});

describe('PlanBudgetReview - the verdict', () => {
  it('reports what is left when the decisions fit', () => {
    renderReview([line()], { r1: { kind: 'buy' } } as PlanDecisionMap);
    fireEvent.change(screen.getByLabelText(/Budget for this round/i), { target: { value: '500' } });
    expect(screen.getByText(/Within budget/i)).toBeInTheDocument();
    expect(screen.getByText(/RM 400/)).toBeInTheDocument();
  });

  it('reports the overrun, and what dropping would fix it', () => {
    const lines = [
      line({ id: 'a', rank: 1 }),
      line({ id: 'b', rank: 2 }),
      line({ id: 'c', rank: 3 }),
    ];
    renderReview(lines, {
      a: { kind: 'buy' }, b: { kind: 'buy' }, c: { kind: 'buy' },
    } as PlanDecisionMap);
    fireEvent.change(screen.getByLabelText(/Budget for this round/i), { target: { value: '250' } });
    expect(screen.getByText(/Over by/i)).toBeInTheDocument();
    expect(screen.getByText(/would bring it inside the budget/i)).toBeInTheDocument();
  });

  it('qualifies a pass when a decided line could not be priced', () => {
    // A clean "Within budget" over lines nobody could cost is arithmetically true and
    // misleading - the missing lines could cost anything.
    renderReview([line({ unit_cost: null, cash_impact: null })], {
      r1: { kind: 'buy' },
    } as PlanDecisionMap);
    fireEvent.change(screen.getByLabelText(/Budget for this round/i), { target: { value: '100' } });
    expect(screen.getByText(/Within budget on what we can price/i)).toBeInTheDocument();
  });

  it('says an unpriced line is missing from the total, in the singular', () => {
    renderReview([line({ unit_cost: null, cash_impact: null })], {
      r1: { kind: 'buy' },
    } as PlanDecisionMap);
    expect(screen.getByText(/1 of the lines you are buying has no price/i)).toBeInTheDocument();
  });
});
