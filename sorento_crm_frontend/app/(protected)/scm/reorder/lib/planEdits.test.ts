/**
 * The draft map's own arithmetic (plan 4.5, UAC C6/D7/E5, R14).
 *
 * The counts are the part most worth pinning: `decided_count` used to be one per
 * RECOMMENDATION, so a product sitting in three bins read as three and the header jumped by
 * three when a buyer decided it once. Everything here counts distinct products.
 */
import { describe, it, expect } from 'vitest';
import { recToPlanLine, type PlanLine } from './planLine';
import { groupPlanLinesByChannel } from './planLineGrouping';
import type { ReorderRecommendation } from '../types/reorder.types';
import type { PlanDecisionMap } from './planDecisions';
import {
  confirmSummary,
  editedProductCount,
  hasRowEdit,
  planPillReading,
  recIdsForLine,
  suggestedDecisionFor,
  summariseMix,
  type PlanRowEditMap,
} from './planEdits';

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
    segment: 'dealer',
    ...over,
  } as ReorderRecommendation;
}

const line = (over: Partial<ReorderRecommendation> = {}): PlanLine => recToPlanLine(rec(over));

describe('suggestedDecisionFor', () => {
  it('rounds the buy to the MOQ and the order multiple, wherever it is read', () => {
    const l = line({ order_qty: 23, moq: 100, order_multiple: 50 });
    expect(suggestedDecisionFor(l).buy).toBe(100);
  });

  it('rounds a fractional demand UP - down would be a deliberate under-buy', () => {
    expect(suggestedDecisionFor(line({ order_qty: 23.2 })).buy).toBe(24);
  });
});

describe('summariseMix', () => {
  it('says each part it carries, in the order stock, PO, buy', () => {
    expect(summariseMix({ stock: { qty: 10, sources: [] }, buy: 90 })).toBe('Stock 10 + Buy 90');
    expect(summariseMix({ buy: 200 })).toBe('Buy 200');
    expect(summariseMix({ skip: true })).toBe('Skipped');
  });
});

describe('planPillReading (C6)', () => {
  const suggested = { buy: 31 };

  it('an untouched row reads Suggested, with the engine mixture', () => {
    expect(planPillReading(undefined, undefined, suggested)).toEqual({
      state: 'suggested', label: 'Suggested', mix: 'Buy 31',
    });
  });

  it('a persisted row reads Saved', () => {
    expect(planPillReading(undefined, { buy: 20 }, suggested).state).toBe('saved');
  });

  it('a confirmed row outranks a merely saved one', () => {
    expect(planPillReading(undefined, { buy: 20, confirmed: true }, suggested).state).toBe(
      'confirmed',
    );
  });

  it('an unsaved edit outranks everything - that is the number on screen', () => {
    const reading = planPillReading({ decision: { buy: 200 } }, { buy: 20 }, suggested);
    expect(reading).toEqual({ state: 'unsaved', label: 'Unsaved', mix: 'Buy 200' });
  });

  it('an edit that touches only the MOQ still reads Unsaved, against the standing mixture', () => {
    expect(planPillReading({ moq: 100 }, { buy: 20 }, suggested)).toEqual({
      state: 'unsaved', label: 'Unsaved', mix: 'Buy 20',
    });
  });

  it('a skip reads Skipped', () => {
    expect(planPillReading(undefined, { skip: true }, suggested).state).toBe('skipped');
  });
});

describe('hasRowEdit', () => {
  it('an absent or empty entry is not an edit, and must not count towards Save', () => {
    expect(hasRowEdit(undefined)).toBe(false);
    expect(hasRowEdit({})).toBe(false);
  });

  it('a cleared field IS an edit - null withdraws an override', () => {
    expect(hasRowEdit({ moq: null })).toBe(true);
    expect(hasRowEdit({ lifecycle: null })).toBe(true);
  });
});

describe('editedProductCount (R14)', () => {
  it('counts PRODUCTS, so one product across three bins decided once reads 1', () => {
    const members = [
      line({ id: 'r1', warehouse_id: 'w1', warehouse_code: 'BRW' }),
      line({ id: 'r2', warehouse_id: 'w2', warehouse_code: 'BRW-BB' }),
      line({ id: 'r3', warehouse_id: 'w3', warehouse_code: 'BRW-AM' }),
    ];
    const edits: PlanRowEditMap = { r1: { decision: { buy: 5 } } };
    expect(editedProductCount(edits, members)).toBe(1);
  });

  it('counts two products as two', () => {
    const lines = [
      line({ id: 'r1', product_id: 'p1' }),
      line({ id: 'r2', product_id: 'p2', sku: 'SKU-2' }),
    ];
    const edits: PlanRowEditMap = { r1: { moq: 100 }, r2: { lifecycle: 'discontinue' } };
    expect(editedProductCount(edits, lines)).toBe(2);
  });

  it('counts a grouped product row once, under the id the grid writes it against', () => {
    const grouped = groupPlanLinesByChannel([
      line({ id: 'r1', warehouse_id: 'w1', warehouse_code: 'BRW' }),
      line({ id: 'r2', warehouse_id: 'w2', warehouse_code: 'BRW-BB' }),
    ]);
    const groupRow = grouped.find((l) => l.id.startsWith('group:')) as PlanLine;
    expect(editedProductCount({ [groupRow.id]: { moq: 50 } }, grouped)).toBe(1);
  });
});

describe('recIdsForLine', () => {
  it('a grouped row fans out to every member recommendation', () => {
    const grouped = groupPlanLinesByChannel([
      line({ id: 'r1', warehouse_id: 'w1', warehouse_code: 'BRW' }),
      line({ id: 'r2', warehouse_id: 'w2', warehouse_code: 'BRW-BB' }),
    ]);
    const groupRow = grouped.find((l) => l.id.startsWith('group:')) as PlanLine;
    expect(recIdsForLine(groupRow).sort()).toEqual(['r1', 'r2']);
  });

  it('an ungrouped row writes to itself', () => {
    expect(recIdsForLine(line())).toEqual(['r1']);
  });
});

describe('confirmSummary (R3, E5)', () => {
  const amended = line({ id: 'r1', product_id: 'p1', sku: 'A', order_qty: 10 });
  const untouched = line({ id: 'r2', product_id: 'p2', sku: 'B', order_qty: 20 });
  const skipped = line({ id: 'r3', product_id: 'p3', sku: 'C', order_qty: 30 });
  const lines = [amended, untouched, skipped];

  it('covers an untouched product as the engine suggestion and leaves a skipped one out', () => {
    const edits: PlanRowEditMap = { r1: { decision: { buy: 15 } } };
    const decisions: PlanDecisionMap = { r3: { skip: true } };
    expect(confirmSummary(edits, decisions, lines).products).toBe(2);
  });

  it('a skip drafted but not yet saved is excluded too', () => {
    const edits: PlanRowEditMap = { r3: { decision: { skip: true } } };
    expect(confirmSummary(edits, {}, lines).products).toBe(2);
  });

  it('leaves out a row with nothing to buy - Confirm would draft nothing for it', () => {
    // Covered entirely from stock: Confirm records the decision and drafts no purchase
    // order line, so counting it made the button promise a purchase it never made (and
    // stay enabled over a plan with nothing left to buy).
    const covered = line({ id: 'r1', product_id: 'p1', order_qty: 10 });
    const buys = line({ id: 'r2', product_id: 'p2', sku: 'B', order_qty: 20 });
    const edits: PlanRowEditMap = {
      r1: { decision: { stock: { qty: 10, sources: [] } } },
    };

    const summary = confirmSummary(edits, {}, [covered, buys]);
    expect(summary.products).toBe(1);
  });

  it('counts nothing at all when every row is covered', () => {
    const covered = line({ id: 'r1', product_id: 'p1', order_qty: 10 });
    const edits: PlanRowEditMap = { r1: { decision: { po: 10 } } };
    expect(confirmSummary(edits, {}, [covered]).products).toBe(0);
  });

  it('leaves out a row already confirmed into a draft purchase order', () => {
    // Confirming again reconciles it to the same line, so the button would stay live over
    // a plan where every row already reads Confirmed.
    const decisions: PlanDecisionMap = {
      r1: { buy: 10, confirmed: true },
      r2: { buy: 20, confirmed: true },
      r3: { skip: true },
    };
    expect(confirmSummary({}, decisions, lines).products).toBe(0);
  });

  it('a new edit on a confirmed row puts it back in the count', () => {
    const decisions: PlanDecisionMap = { r1: { buy: 10, confirmed: true } };
    const edits: PlanRowEditMap = { r1: { decision: { buy: 40 } } };
    expect(confirmSummary(edits, decisions, [amended]).products).toBe(1);
  });

  it('prices the buys it can and counts the ones it cannot, never summing them as zero', () => {
    const priced = line({ id: 'r1', product_id: 'p1', order_qty: 10, unit_cost: 10, cash_impact: 100 });
    const unpriced = line({
      id: 'r2', product_id: 'p2', sku: 'B', order_qty: 5,
      unit_cost: null, cash_impact: null,
      supplier: null,
    });
    const summary = confirmSummary({}, {}, [priced, unpriced]);
    expect(summary.products).toBe(2);
    expect(summary.cash).toBe(100);
    expect(summary.unpriced).toBe(1);
  });
});
