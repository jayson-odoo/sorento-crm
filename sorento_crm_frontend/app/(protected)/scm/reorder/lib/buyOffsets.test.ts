/**
 * The buy quantity is a proposal, and every offset that reduced it is declinable.
 *
 * The case that drove this, from the live plan: MWB248 at BRW needs 24, has 1 on hand, and
 * the engine showed 23 with no way to say "no, buy 24 and leave that one alone".
 */
import { describe, it, expect } from 'vitest';
import type { ReorderRecommendation } from '../types/reorder.types';
import { recToPlanRow, type M8PlanRow } from './planRow';
import {
  buyOffsetsFor,
  declineReason,
  grossRequirement,
  qtyWithDeclined,
  roundToSupplierTerms,
  type BuyOffsetKey,
} from './buyOffsets';

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

const row = (over: Partial<ReorderRecommendation> = {}): M8PlanRow => recToPlanRow(rec(over));
const declined = (...keys: BuyOffsetKey[]) => new Set<BuyOffsetKey>(keys);

describe('buyOffsetsFor - what the buyer is being asked to agree to', () => {
  it('offers the on-hand unit the engine consumed silently', () => {
    const offsets = buyOffsetsFor(row());
    expect(offsets).toHaveLength(1);
    expect(offsets[0]).toMatchObject({ key: 'on_hand', qty: 1 });
    expect(offsets[0].label).toContain('BRW');
  });

  it('leaves out an offset of zero, which is not a choice', () => {
    // "Incoming SPO 0" is the absence of a suggestion, not one to decline. Listing it would
    // bury the single real choice among empty rows.
    expect(buyOffsetsFor(row()).map((o) => o.key)).toEqual(['on_hand']);
  });

  it('lists every real offset, largest first', () => {
    const offsets = buyOffsetsFor(row({ on_hand: 5, incoming_spo: 40, outstanding_po: 12 }));
    expect(offsets.map((o) => o.key)).toEqual(['incoming_spo', 'outstanding_po', 'on_hand']);
  });

  it('names no location when the row has none, rather than printing an empty one', () => {
    const offsets = buyOffsetsFor(row({ warehouse_code: null, warehouse_name: null }));
    expect(offsets[0].label).toBe('Use what is on hand');
  });
});

describe('grossRequirement - what is needed before anything is netted', () => {
  it('adds the offsets back onto the proposed buy', () => {
    expect(grossRequirement(row())).toBe(24);
  });

  it('equals the buy when nothing was netted', () => {
    expect(grossRequirement(row({ on_hand: 0 }))).toBe(23);
  });
});

describe('qtyWithDeclined - declining an offset adds it back', () => {
  it('buys the whole requirement when the on-hand unit is declined', () => {
    expect(qtyWithDeclined(row(), declined('on_hand'))).toBe(24);
  });

  it('leaves the engine quantity alone when every offset is accepted', () => {
    expect(qtyWithDeclined(row(), declined())).toBe(23);
  });

  it('adds back only what was declined', () => {
    const r = row({ order_qty: 100, on_hand: 5, incoming_spo: 40, outstanding_po: 12 });
    expect(qtyWithDeclined(r, declined('incoming_spo'))).toBe(140);
    expect(qtyWithDeclined(r, declined('incoming_spo', 'on_hand'))).toBe(145);
  });

  it('holds on the reorder-level basis too, because the target is never re-derived', () => {
    // buy = target - net on every basis, so buy' = buy + offset regardless of which target
    // produced it. Same arithmetic, a policy_type the forecast path never sees.
    const r = row({ policy_type: 'reorder_level' as ReorderRecommendation['policy_type'],
                    order_qty: 50, on_hand: 8 });
    expect(qtyWithDeclined(r, declined('on_hand'))).toBe(58);
  });
});

describe('roundToSupplierTerms - the supplier terms survive the buyer decision', () => {
  it('lifts the quantity to the minimum order', () => {
    const r = row({ moq: 50 });
    expect(qtyWithDeclined(r, declined('on_hand'))).toBe(50);
  });

  it('rounds up to a whole order multiple', () => {
    const r = row({ order_multiple: 10 });
    expect(qtyWithDeclined(r, declined('on_hand'))).toBe(30);
  });

  it('applies the minimum first, then the multiple', () => {
    const r = row({ moq: 50, order_multiple: 8 });
    expect(qtyWithDeclined(r, declined('on_hand'))).toBe(56);
  });

  it('never rounds nothing up into a purchase', () => {
    // A minimum order applies once you have decided to order, not to the decision itself.
    expect(roundToSupplierTerms(0, row({ moq: 50 }))).toBe(0);
  });
});

describe('declineReason - the decision has to be readable after the run', () => {
  it('states what was not counted and where, not what the number became', () => {
    expect(declineReason(row(), declined('on_hand'))).toBe(
      'Not counting the 1 on hand at BRW towards this requirement.',
    );
  });

  it('reads as a sentence when several are declined', () => {
    const r = row({ on_hand: 5, incoming_spo: 40 });
    expect(declineReason(r, declined('on_hand', 'incoming_spo'))).toBe(
      'Not counting the 40 incoming or the 5 on hand at BRW towards this requirement.',
    );
  });

  it('is empty when nothing was declined, so no adjustment is staged', () => {
    expect(declineReason(row(), declined())).toBe('');
  });
});
