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
import type { ProductEconomics } from './productHealth';
import {
  confirmSummary,
  editedProductCount,
  hasRowEdit,
  planPillReading,
  recIdsForLine,
  suggestedDecisionFor,
  summariseMix,
  withConfirmLifecycle,
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

  it('reads recommended_qty, not order_qty, for the raw buy (ONE FORMULA, AC-5)', () => {
    // `order_qty` (the frozen, rounded `rounded_qty`) is no longer what the buy is read
    // off - only `recommended_qty` is (the raw, pre-round gap). Overriding `order_qty`
    // alone, with `recommended_qty` left at the fixture's own default (23), leaves the
    // buy unchanged at 23: this pins that `order_qty` itself is not read directly.
    expect(suggestedDecisionFor(line({ order_qty: 23.2 })).buy).toBe(23);
  });
});

describe('one formula (PLAN-reorder-one-formula.md, AC-5)', () => {
  // B2155-NL-BLUE's own figures: on hand 128, PO 339, need 663 (project 493 + retail
  // 170 + level 0), so the engine's own `order_qty` (196) is ALREADY net of both -
  // `suggestedDecisionFor` must read the parts off the line's own frozen fields
  // (`on_hand` / `outstanding_po` / `recommended_qty`), never re-net them through a
  // `cover`/`poReceipts` pair passed in from outside. Called with ONE argument on
  // purpose: the whole point of the fix is that nothing else is needed.
  it('reads Stock/PO/Buy off the line itself, never a second netting', () => {
    const l = line({
      order_qty: 196, recommended_qty: 196, on_hand: 128, outstanding_po: 339,
    });
    expect(suggestedDecisionFor(l)).toEqual({
      stock: { qty: 128, sources: [] },
      po: 339,
      buy: 196,
    });
  });

  // CBMC5570's own figures: level 100, retail 2, PO 1, no stock, no project ->
  // need 102, buy 101. No stock part at all (on_hand 0 is omitted, not `stock: {qty:0}`).
  it('omits a zero stock part and still states PO + Buy', () => {
    const l = line({
      order_qty: 101, recommended_qty: 101, on_hand: 0, outstanding_po: 1,
    });
    const suggested = suggestedDecisionFor(l);
    expect(suggested.stock).toBeUndefined();
    expect(suggested.po).toBe(1);
    expect(suggested.buy).toBe(101);
  });
});

describe('summariseMix (AC-5)', () => {
  it('prints the B2155 mixture "Stock 128 + PO 339 + Buy 196"', () => {
    expect(summariseMix({ stock: { qty: 128, sources: [] }, po: 339, buy: 196 })).toBe(
      'Stock 128 + PO 339 + Buy 196',
    );
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

// S6 (G5 ruling, 9 Sep 2026): "Confirm never sweeps" reverses R3's "an untouched row
// confirms as the engine's suggestion". Every test below is the R3-era pin, RE-PINNED to
// the new rule - the shapes and comments describing each row are kept, only the counts
// (and, where the naming said "as the engine suggestion"/"sweep", the names) changed.
describe('confirmSummary (G5 - never sweeps an undecided row)', () => {
  const amended = line({ id: 'r1', product_id: 'p1', sku: 'A', order_qty: 10 });
  const untouched = line({ id: 'r2', product_id: 'p2', sku: 'B', order_qty: 20 });
  const skipped = line({ id: 'r3', product_id: 'p3', sku: 'C', order_qty: 30 });
  const lines = [amended, untouched, skipped];

  it('counts only the decided product; an untouched one and a persisted-skip one are excluded', () => {
    const edits: PlanRowEditMap = { r1: { decision: { buy: 15 } } };
    const decisions: PlanDecisionMap = { r3: { skip: true } };
    expect(confirmSummary(edits, decisions, lines).products).toBe(1);
  });

  it('a drafted skip and two untouched rows all count 0 - nothing here was decided to buy', () => {
    const edits: PlanRowEditMap = { r3: { decision: { skip: true } } };
    expect(confirmSummary(edits, {}, lines).products).toBe(0);
  });

  it('a decided-but-covered row is excluded, and the untouched sibling never sweeps in', () => {
    // Covered entirely from stock: Confirm records the decision and drafts no purchase
    // order line, so counting it made the button promise a purchase it never made.
    const covered = line({ id: 'r1', product_id: 'p1', order_qty: 10 });
    const buys = line({ id: 'r2', product_id: 'p2', sku: 'B', order_qty: 20 });
    const edits: PlanRowEditMap = {
      r1: { decision: { stock: { qty: 10, sources: [] } } },
    };

    const summary = confirmSummary(edits, {}, [covered, buys]);
    expect(summary.products).toBe(0);
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

  it('mixes all five row shapes on one plan: only the confirmed-and-re-edited row counts', () => {
    // `cash_impact` set so each line's own `unit_cost_base` (`cash_impact / order_qty`,
    // `planRow.recToPlanRow`) comes out to a round 10, so the assertion below reads
    // straight off the buy quantities rather than the fixture's own unrelated defaults.
    // (a) already confirmed, no new edit -> excluded.
    const confirmedNoEdit = line({ id: 'r1', product_id: 'p1', sku: 'A', order_qty: 10, cash_impact: 100 });
    // (b) confirmed, then edited again -> included at the EDITED quantity.
    const confirmedEdited = line({ id: 'r2', product_id: 'p2', sku: 'B', order_qty: 10, cash_impact: 100 });
    // (c) skipped -> excluded.
    const skipped = line({ id: 'r3', product_id: 'p3', sku: 'C', order_qty: 30, cash_impact: 300 });
    // (d) untouched, the engine's own mixture would have been a buy -> excluded (G5:
    // nobody decided this row).
    const untouchedBuy = line({ id: 'r4', product_id: 'p4', sku: 'D', order_qty: 20, cash_impact: 200 });
    // (e) untouched, fully covered from stock (buy 0) -> excluded either way.
    const untouchedStockOnly = line({ id: 'r5', product_id: 'p5', sku: 'E', order_qty: 15, cash_impact: 150 });
    const rows = [confirmedNoEdit, confirmedEdited, skipped, untouchedBuy, untouchedStockOnly];

    const decisions: PlanDecisionMap = {
      r1: { buy: 10, confirmed: true },
      r2: { buy: 10, confirmed: true },
      r3: { skip: true },
    };
    const edits: PlanRowEditMap = {
      r2: { decision: { buy: 25 } },
    };

    const summary = confirmSummary(edits, decisions, rows);

    expect(summary.products).toBe(1); // (b) only
    // unit_cost_base is 10 on every line above: 10 * 25 (b, the EDITED buy).
    expect(summary.cash).toBe(250);
    expect(summary.unpriced).toBe(0);
  });

  it('an untouched priced row and an untouched unpriced row both count 0 - neither was decided', () => {
    const priced = line({ id: 'r1', product_id: 'p1', order_qty: 10, unit_cost: 10, cash_impact: 100 });
    const unpriced = line({
      id: 'r2', product_id: 'p2', sku: 'B', order_qty: 5,
      unit_cost: null, cash_impact: null,
      supplier: null,
    });
    const summary = confirmSummary({}, {}, [priced, unpriced]);
    expect(summary.products).toBe(0);
    expect(summary.cash).toBe(0);
    expect(summary.unpriced).toBe(0);
  });
});

// ===========================================================================
// S6 (reorder-feedback-9sep.md, G5 ruling 9 Sep 2026) - Confirm never sweeps.
// `effective = edit?.decision ?? persisted`, with no `suggestedDecisionFor` fallback:
// a row nobody decided (no drafted edit, no persisted decision) counts as 0 products,
// however the engine itself would have sized it. Every `describe('confirmSummary (R3,
// E5)')` test above still asserts the OLD sweep-in behaviour and needs re-pinning once
// this lands (see the tester's report for the full flip list).
// ===========================================================================

describe('confirmSummary (AC-S6.4, G5 - suggested-only rows are never counted)', () => {
  it('a row with only the engine suggestion - no drafted edit, no persisted decision - counts 0 products', () => {
    const suggestedOnly = line({ id: 'r9', product_id: 'p9', sku: 'Z', order_qty: 20 });
    const summary = confirmSummary({}, {}, [suggestedOnly]);
    expect(summary.products).toBe(0);
    expect(summary.cash).toBe(0);
    expect(summary.unpriced).toBe(0);
  });

  it('a decided row still counts beside an undecided, suggested-only sibling', () => {
    const decided = line({ id: 'r1', product_id: 'p1', sku: 'A', order_qty: 10 });
    const suggestedOnly = line({ id: 'r2', product_id: 'p2', sku: 'B', order_qty: 20 });
    const edits: PlanRowEditMap = { r1: { decision: { buy: 10 } } };

    const summary = confirmSummary(edits, {}, [decided, suggestedOnly]);

    expect(summary.products).toBe(1);
  });
});

// ===========================================================================
// S8 (reorder-feedback-9sep.md, G4 ruling 9 Sep 2026) - "the preselected health
// suggestion persists on Confirm": `withConfirmLifecycle` fills the SAME suggestion
// `suggestedLifecycle` computes into every row `confirmableLines` would actually draft,
// leaving a row the buyer already answered (or one Confirm is not touching) exactly as
// it was.
// ===========================================================================

function econ(over: Partial<ProductEconomics> = {}): ProductEconomics {
  return {
    product_id: 'p1', avg_sell_price: null, sell_source: null, sold_qty: 0, on_hand: 0,
    avg_monthly_out: 0, turnover_months: null, no_movement: true, lifecycle_decision: null,
    lifecycle_decided_at: null, sold_recent_qty: 0, bought_recent_qty: 0,
    movement_class: 'dead',
    ...over,
  };
}

describe('withConfirmLifecycle (AC-S8.2/S8.3)', () => {
  it('fills the class-based suggestion for a decided row the buyer never answered', () => {
    const decided = line({ id: 'r1', product_id: 'p1', order_qty: 10 });
    const edits: PlanRowEditMap = { r1: { decision: { buy: 10 } } };
    const economicsFor = () => econ({ movement_class: 'dead' });

    const augmented = withConfirmLifecycle(edits, {}, [decided], economicsFor);

    expect(augmented.r1).toMatchObject({ decision: { buy: 10 }, lifecycle: 'discontinue' });
  });

  it('a stored lifecycle_decision wins over the class-based suggestion', () => {
    const decided = line({ id: 'r1', product_id: 'p1', order_qty: 10 });
    const edits: PlanRowEditMap = { r1: { decision: { buy: 10 } } };
    const economicsFor = () => econ({ movement_class: 'dead', lifecycle_decision: 'keep' });

    const augmented = withConfirmLifecycle(edits, {}, [decided], economicsFor);

    expect(augmented.r1).toMatchObject({ lifecycle: 'keep' });
  });

  it('leaves an explicit buyer answer alone, including a withdrawal to null', () => {
    const decided = line({ id: 'r1', product_id: 'p1', order_qty: 10 });
    const edits: PlanRowEditMap = { r1: { decision: { buy: 10 }, lifecycle: null } };
    const economicsFor = () => econ({ movement_class: 'dead' });

    const augmented = withConfirmLifecycle(edits, {}, [decided], economicsFor);

    expect(augmented.r1).toMatchObject({ lifecycle: null });
  });

  it('writes nothing for a row Confirm is not drafting (untouched, or skipped)', () => {
    const untouched = line({ id: 'r1', product_id: 'p1', order_qty: 10 });
    const skipped = line({ id: 'r2', product_id: 'p2', sku: 'B', order_qty: 20 });
    const edits: PlanRowEditMap = { r2: { decision: { skip: true } } };
    const economicsFor = () => econ({ movement_class: 'dead' });

    const augmented = withConfirmLifecycle(edits, {}, [untouched, skipped], economicsFor);

    expect(augmented.r1).toBeUndefined();
    expect(augmented.r2).toEqual(edits.r2);
  });

  it('defaults to keep with no economics on file at all - never discontinues by accident', () => {
    const decided = line({ id: 'r1', product_id: 'p1', order_qty: 10 });
    const edits: PlanRowEditMap = { r1: { decision: { buy: 10 } } };

    const augmented = withConfirmLifecycle(edits, {}, [decided]);

    expect(augmented.r1).toMatchObject({ lifecycle: 'keep' });
  });
});
