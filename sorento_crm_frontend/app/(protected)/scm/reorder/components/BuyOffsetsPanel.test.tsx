/**
 * The panel that turns a silently-netted quantity back into a proposal.
 *
 * MWB248 at BRW: needs 24, 1 on hand, engine says buy 23. The buyer has to be able to see
 * that the 1 was used, and say no to it.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { ReorderRecommendation } from '../types/reorder.types';
import { recToPlanRow } from '../lib/planRow';
import { BuyOffsetsPanel } from './BuyOffsetsPanel';

function rec(over: Partial<ReorderRecommendation> = {}): ReorderRecommendation {
  return {
    id: 'rec-1', type: 'buy', sku: 'MWB248', product_name: 'MWB248',
    abc_class: null, xyz_class: null, warehouse_code: 'BRW', warehouse_name: 'Butterworth',
    product_id: 'p1', warehouse_id: 'w1', is_network: false, allocation: null,
    order_qty: 23, recommended_qty: 23, reorder_point: 0, min_qty: null, max_qty: null,
    order_up_to: 0, net_position: -23, days_of_cover: null, reason: 'reorder_point',
    reason_label: 'net -23 <= ROP 0', confidence: 'low', sample_size: 0,
    supplier: { supplier_code: 'DEFAULT', supplier_name: 'DEFAULT', unit_cost: null,
                lead_time_days: 90, composite_score: 0, is_primary: true },
    alternatives: [], is_exception: false, disposition_action: null, transfer_flag: null,
    forecast_daily_demand: 0, lead_time_days: 90, lead_time_source: 'default',
    safety_stock: 0, safety_stock_method: null, safety_stock_fallback: null,
    service_level: null, safety_days: 7, review_days: 30,
    moq: null, order_multiple: null, policy_type: 'reorder_point', supplier_selection: 'primary',
    unit_cost: null, cash_impact: null, rank: 878, rank_score: 0, funding_status: null,
    days_to_stockout: null, rank_factors: [],
    on_hand: 1, incoming_spo: 0, outstanding_po: 0, outstanding_sales: 24,
    ...over,
  } as ReorderRecommendation;
}

function renderPanel(over: Partial<ReorderRecommendation> = {}, onApply = vi.fn()) {
  render(<BuyOffsetsPanel row={recToPlanRow(rec(over))} onApply={onApply} />);
  return { onApply };
}

beforeEach(() => vi.clearAllMocks());

describe('BuyOffsetsPanel - the netting is visible', () => {
  it('shows the requirement, not just the result', () => {
    renderPanel();
    expect(screen.getByText('Needed')).toBeInTheDocument();
    expect(screen.getByText('24')).toBeInTheDocument();
  });

  it('shows the on-hand unit as a ticked suggestion, with where it is', () => {
    renderPanel();
    const box = screen.getByRole('checkbox', { name: /on hand at BRW/i });
    expect(box).toBeChecked();
    expect(screen.getByText('-1')).toBeInTheDocument();
  });

  it('says so plainly when there was nothing to net', () => {
    renderPanel({ on_hand: 0 });
    expect(screen.getByText(/Nothing on hand, incoming, or on order/i)).toBeInTheDocument();
    expect(screen.queryByRole('checkbox')).toBeNull();
  });
});

describe('BuyOffsetsPanel - declining a suggestion', () => {
  it('raises the buy back to the full requirement', () => {
    renderPanel();
    fireEvent.click(screen.getByRole('checkbox', { name: /on hand at BRW/i }));
    expect(screen.getByRole('button', { name: /Buy 24 instead/i })).toBeInTheDocument();
  });

  it('offers no action until something actually changes', () => {
    renderPanel();
    expect(screen.queryByRole('button', { name: /instead/i })).toBeNull();
  });

  it('stages the adjustment with the quantity AND the reason', () => {
    // The reason is the point: six weeks later "qty 23 to 24" explains nothing, and the
    // buyer's actual decision - that the unit on the shelf was not usable - is the record.
    const { onApply } = renderPanel();
    fireEvent.click(screen.getByRole('checkbox', { name: /on hand at BRW/i }));
    fireEvent.click(screen.getByRole('button', { name: /Buy 24 instead/i }));
    expect(onApply).toHaveBeenCalledWith(
      24,
      'Not counting the 1 on hand at BRW towards this requirement.',
    );
  });

  it('re-applies the supplier terms to the buyer decision', () => {
    renderPanel({ moq: 50 });
    fireEvent.click(screen.getByRole('checkbox', { name: /on hand at BRW/i }));
    expect(screen.getByRole('button', { name: /Buy 50 instead/i })).toBeInTheDocument();
  });

  it('can be undone before it is applied', () => {
    const { onApply } = renderPanel();
    const box = screen.getByRole('checkbox', { name: /on hand at BRW/i });
    fireEvent.click(box);
    fireEvent.click(box);
    expect(screen.queryByRole('button', { name: /instead/i })).toBeNull();
    expect(onApply).not.toHaveBeenCalled();
  });
});
