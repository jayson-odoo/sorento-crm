/**
 * SCM M8 - plan-row adapters (Phase 2, test-first).
 * `recToPlanRow` / `recToDispositionRow` / `m8CashImpact` / `supplierOptionsFor`
 * map the REAL run payload onto the lean M8 grid rows the div-grid renders.
 *   M8-C11 Warehouse column · M8-A4 order-qty inputs · M8-C12 Stock allocation rows
 *   M8-A6 no UUIDs (human warehouse labels) · needs-cost supplier options are costed-only
 */
import { describe, it, expect } from 'vitest';
import type { ReorderRecommendation, SupplierChoice } from '../types/reorder.types';
import {
  isActionableDisposition,
  m8CashImpact,
  recToDispositionRow,
  recToPlanRow,
  splitDispositionRows,
  supplierOptionsFor,
  type M8DispositionRow,
  type M8PlanRow,
} from './planRow';

const acme: SupplierChoice = {
  supplier_code: 'SUP-ACME',
  supplier_name: 'Acme Sanitary',
  unit_cost: 42,
  lead_time_days: 14,
  composite_score: 88,
  is_primary: true,
};
const beta: SupplierChoice = {
  supplier_code: 'SUP-BETA',
  supplier_name: 'Beta Supplies',
  unit_cost: 38,
  lead_time_days: 21,
  composite_score: 80,
  is_primary: false,
};
/** An uncosted alternative - must be dropped from swap options (can't be budgeted). */
const nocost: SupplierChoice = {
  supplier_code: 'SUP-NOCOST',
  supplier_name: 'Gamma (no price)',
  unit_cost: null,
  lead_time_days: 30,
  composite_score: null,
  is_primary: false,
};

function rec(over: Partial<ReorderRecommendation> = {}): ReorderRecommendation {
  return {
    id: 'rec-1',
    type: 'buy',
    sku: 'CW-BASIN-450',
    product_name: 'Ceramic Wash Basin 450mm',
    abc_class: 'A',
    xyz_class: 'X',
    warehouse_code: 'WH-KL',
    warehouse_name: 'Kuala Lumpur DC',
    product_id: 'prod-uuid-1',
    warehouse_id: 'wh-uuid-1',
    is_network: false,
    allocation: null,
    order_qty: 320,
    recommended_qty: 300,
    reorder_point: 280,
    min_qty: null,
    max_qty: null,
    order_up_to: 600,
    net_position: 240,
    days_of_cover: 20,
    reason: 'reorder_point',
    reason_label: 'net ≤ ROP',
    confidence: 'high',
    sample_size: 40,
    supplier: acme,
    alternatives: [beta],
    is_exception: false,
    disposition_action: null,
    transfer_flag: null,
    forecast_daily_demand: 12,
    lead_time_days: 14,
    lead_time_source: 'measured',
    safety_stock: 77,
    safety_stock_method: 'fixed_days',
    safety_stock_fallback: null,
    service_level: 0.95,
    safety_days: 7,
    review_days: 30,
    moq: 10,
    order_multiple: 5,
    policy_type: 'reorder_point',
    supplier_selection: 'primary',
    unit_cost: 42,
    cash_impact: 320 * 42,
    rank: 3,
    rank_score: 0.8,
    funding_status: null,
    days_to_stockout: 20,
    rank_factors: [],
    ...over,
  };
}

describe('recToPlanRow (M8 adapter)', () => {
  it('maps the frozen numbers + order-qty inputs onto the grid row (M8-A4)', () => {
    const row = recToPlanRow(rec());
    expect(row.id).toBe('rec-1');
    expect(row.rank).toBe(3);
    expect(row.sku).toBe('CW-BASIN-450');
    expect(row.order_qty).toBe(320);
    // The engine's frozen qty is preserved for the struck-through "was" display.
    expect(row.original_order_qty).toBe(320);
    expect(row.unit_cost).toBe(42);
    expect(row.net).toBe(240);
    expect(row.days_cover).toBe(20);
    expect(row.forecast_daily_demand).toBe(12);
    // M8-A4 - order-qty drill reads these off the frozen rec, never recomputed.
    expect(row.order_qty_inputs).toEqual({
      safety_stock: 77,
      reorder_point: 280,
      order_up_to: 600,
      rounded_qty: 320,
      moq: 10,
      order_multiple: 5,
    });
    // data-only ids for the demand drill (never rendered)
    expect(row.product_id).toBe('prod-uuid-1');
    expect(row.warehouse_id).toBe('wh-uuid-1');
  });

  it('renders a human warehouse label for a per-warehouse row (M8-C11 / M8-A6, no UUID)', () => {
    expect(recToPlanRow(rec()).warehouse).toBe('Kuala Lumpur DC');
  });

  it('labels a network (aggregated) row "Network" (M8-C11)', () => {
    const row = recToPlanRow(rec({ is_network: true, warehouse_code: null, warehouse_name: null }));
    expect(row.warehouse).toBe('Network');
  });

  it('carries the chosen supplier onto the row', () => {
    const row = recToPlanRow(rec());
    expect(row.supplier).toEqual({
      code: 'SUP-ACME',
      name: 'Acme Sanitary',
      unit_cost: 42,
      lead_time_days: 14,
    });
  });

  it('falls back to "No supplier" + null cost on an unpriced rec', () => {
    const row = recToPlanRow(rec({ supplier: null, unit_cost: null }));
    expect(row.supplier.name).toBe('No supplier');
    expect(row.unit_cost).toBeNull();
  });
});

describe('supplierOptionsFor - costed swap options only', () => {
  it('includes the chosen supplier + costed alternatives, drops uncosted + dupes', () => {
    const opts = supplierOptionsFor(rec({ supplier: acme, alternatives: [beta, nocost, acme] }));
    // acme (chosen) + beta; nocost dropped (no price); acme not duplicated
    expect(opts.map((o) => o.value)).toEqual(['SUP-ACME', 'SUP-BETA']);
    expect(opts.find((o) => o.value === 'SUP-BETA')).toMatchObject({
      value: 'SUP-BETA', // supplier CODE - what /adjust's override_supplier_id wants
      label: 'Beta Supplies',
      unit_cost: 38,
      lead_time_days: 21,
    });
  });

  it('carries the currency of each option, so a price can be written as what it is', () => {
    // Without it the shortlist prints bare numbers and a USD 8.00 alternative reads
    // cheaper than an RM 10.00 chosen supplier, which is the opposite of the truth.
    const usd: SupplierChoice = {
      ...beta,
      unit_cost: 8,
      currency: 'USD',
      unit_cost_base: 36,
      base_currency: 'MYR',
    };
    const opts = supplierOptionsFor(rec({ supplier: acme, alternatives: [usd] }));

    expect(opts.find((o) => o.value === 'SUP-BETA')).toMatchObject({
      unit_cost: 8,
      currency: 'USD',
      unit_cost_base: 36,
    });
  });

  it('leaves the currency absent when the payload carries none', () => {
    // An older run has no currency on the choice; that figure already meant ringgit and
    // is rendered as base, never as a bare number.
    const opts = supplierOptionsFor(rec({ supplier: acme, alternatives: [beta] }));

    expect(opts.find((o) => o.value === 'SUP-BETA')?.currency).toBeNull();
  });
});

describe('m8CashImpact - live qty x the price in the budget currency', () => {
  it('multiplies live qty by the converted unit cost', () => {
    expect(m8CashImpact({ order_qty: 320, unit_cost: 42, unit_cost_base: 42 })).toBe(13440);
  });
  it('is null when the row is uncosted', () => {
    expect(m8CashImpact({ order_qty: 320, unit_cost: null, unit_cost_base: null })).toBeNull();
  });
});

describe('recToDispositionRow (M8-C12 Stock allocation rows)', () => {
  it('maps a hold disposition with qty from net_position + human warehouse', () => {
    const row = recToDispositionRow(
      rec({
        type: 'disposition',
        disposition_action: 'hold',
        net_position: 640,
        reason_label: 'days-of-cover > 180',
        order_qty: null,
      }),
    );
    expect(row.action).toBe('hold');
    expect(row.qty).toBe(640);
    expect(row.warehouse_name).toBe('Kuala Lumpur DC');
    expect(row.reason).toBe('days-of-cover > 180');
  });

  it('maps discontinue + promo actions', () => {
    expect(recToDispositionRow(rec({ disposition_action: 'discontinue' })).action).toBe('discontinue');
    expect(recToDispositionRow(rec({ disposition_action: 'promo' })).action).toBe('promo');
  });

  it('labels a network disposition row "Network"', () => {
    const row = recToDispositionRow(
      rec({ is_network: true, warehouse_code: null, warehouse_name: null, disposition_action: 'hold' }),
    );
    expect(row.warehouse_code).toBe('Network');
  });
});

describe('splitDispositionRows (M8-F18 actionable vs FYI hold)', () => {
  function drow(id: string, action: M8DispositionRow['action']): M8DispositionRow {
    return {
      id,
      sku: `SKU-${id}`,
      product_name: `Product ${id}`,
      action,
      qty: 100,
      warehouse_code: 'WH-KL',
      warehouse_name: 'Kuala Lumpur DC',
      days_cover: 900,
      reason: 'overstock',
    };
  }

  it('classifies discontinue + promo as actionable and hold as FYI', () => {
    expect(isActionableDisposition('discontinue')).toBe(true);
    expect(isActionableDisposition('promo')).toBe(true);
    expect(isActionableDisposition('hold')).toBe(false);
  });

  it('splits a mixed list, preserving order within each group', () => {
    const rows = [
      drow('a', 'hold'),
      drow('b', 'discontinue'),
      drow('c', 'hold'),
      drow('d', 'promo'),
      drow('e', 'hold'),
    ];
    const { actionable, hold } = splitDispositionRows(rows);
    expect(actionable.map((r) => r.id)).toEqual(['b', 'd']);
    expect(hold.map((r) => r.id)).toEqual(['a', 'c', 'e']);
  });

  it('yields an empty actionable list when every row is hold', () => {
    const { actionable, hold } = splitDispositionRows([drow('a', 'hold'), drow('b', 'hold')]);
    expect(actionable).toHaveLength(0);
    expect(hold).toHaveLength(2);
  });
});

describe('m8CashImpact - the live cash figure is in the budget currency', () => {
  // The budget is one pot of ringgit. A USD row costed at its face value consumes a
  // quarter of what it really does, so a buyer sliding the budget "funds" a plan they
  // cannot pay for. The row therefore carries BOTH prices: what the supplier charges,
  // and what it converts to.

  const row = (over: Partial<M8PlanRow> = {}): Pick<
    M8PlanRow,
    'order_qty' | 'unit_cost' | 'unit_cost_base'
  > => ({
    order_qty: 10,
    unit_cost: 45,
    unit_cost_base: 198,
    ...over,
  });

  it('converts before multiplying, so 10 x USD 45 is 1980 not 450', () => {
    expect(m8CashImpact(row())).toBe(1980);
  });

  it('is unchanged for a price already in the budget currency', () => {
    expect(m8CashImpact(row({ unit_cost: 190, unit_cost_base: 190 }))).toBe(1900);
  });

  it('has no figure when the price could not be converted', () => {
    // Face value here would be a wrong number that funds; null is the honest answer and
    // parks the row in front of a human.
    expect(m8CashImpact(row({ unit_cost_base: null }))).toBeNull();
  });

  it('has no figure when nobody has priced the item', () => {
    expect(m8CashImpact(row({ unit_cost: null, unit_cost_base: null }))).toBeNull();
  });

  it('costs a free item at zero rather than calling it unknown', () => {
    expect(m8CashImpact(row({ unit_cost: 0, unit_cost_base: 0 }))).toBe(0);
  });
});
