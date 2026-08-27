/**
 * Product-grain channel grouping (5.3, follow-up 19-20 Aug: SUPERSEDES the (product,channel)
 * cut). Reproduces the captain's TPE-9204 complaint - a bare-site Retail row and two
 * suffixed-bin Project rows for one product - but the refined ask is ONE row per PRODUCT
 * with Project/Retail as dynamic COLUMNS on that one row, not a row per channel.
 */
import { describe, it, expect } from 'vitest';
import type { ReorderRecommendation } from '../types/reorder.types';
import { recToPlanLine, type PlanLine } from './planLine';
import {
  channelOf,
  groupPlanLinesByChannel,
  isGroupedLine,
  locationLabel,
  presentChannels,
} from './planLineGrouping';

function rec(over: Partial<ReorderRecommendation> = {}): ReorderRecommendation {
  return {
    id: 'r1', type: 'buy', sku: 'TPE-9204', product_name: 'Toilet paper enclosure',
    abc_class: null, xyz_class: null, warehouse_code: 'BRW', warehouse_name: 'Butterworth',
    product_id: 'p1', warehouse_id: 'w1', is_network: false, allocation: null,
    order_qty: 10, recommended_qty: 10, reorder_point: 0, min_qty: null, max_qty: null,
    order_up_to: 0, net_position: -10, days_of_cover: null, reason: 'reorder_point',
    reason_label: '', confidence: 'low', sample_size: 0,
    supplier: { supplier_code: 'S1', supplier_name: 'Acme', unit_cost: 10,
                lead_time_days: 30, composite_score: 0, is_primary: true },
    alternatives: [], is_exception: false, disposition_action: null, transfer_flag: null,
    forecast_daily_demand: 1, lead_time_days: 30, lead_time_source: 'default',
    safety_stock: 2, safety_stock_method: null, safety_stock_fallback: null,
    service_level: null, safety_days: 0, review_days: 0,
    moq: null, order_multiple: null, policy_type: 'reorder_point', supplier_selection: 'primary',
    unit_cost: 10, cash_impact: 100, rank: 1, rank_score: 0, funding_status: null,
    days_to_stockout: null, rank_factors: [],
    on_hand: 1, incoming_spo: 0, outstanding_po: 0, outstanding_sales: 5,
    segment: 'dealer',
    project_need: 0, retail_need: 0,
    project_committed: 0, retail_committed: 0,
    ...over,
  } as ReorderRecommendation;
}

const line = (over: Partial<ReorderRecommendation> = {}): PlanLine => recToPlanLine(rec(over));

describe('channelOf', () => {
  it('maps the bare-site dealer segment to retail', () => {
    expect(channelOf(line({ segment: 'dealer' }))).toBe('retail');
  });
  it('maps the suffixed-bin project segment to project', () => {
    expect(channelOf(line({ segment: 'project' }))).toBe('project');
  });
  it('reads a site with no persisted segment as retail, the same call the engine makes', () => {
    // `reorder_run_service` nets on `COALESCE(w.segment, 'dealer') <> 'project'`, so an
    // untagged bin is already planned as dealer stock. It used to read Unclassified here
    // and nowhere else, which grew a column for a missing tag (captain, P4: "nothing
    // should be unclassified").
    expect(channelOf(line({ segment: null }))).toBe('retail');
  });
});

describe('locationLabel', () => {
  it('joins codes while short', () => {
    expect(locationLabel(['BRW-IB', 'BRW-IR'])).toBe('BRW-IB, BRW-IR');
  });
  it('falls back to a count once the list gets long', () => {
    expect(locationLabel(['A', 'B', 'C', 'D'])).toBe('4 locations');
  });
});

describe('presentChannels', () => {
  it('is Project then Retail, in fixed order, never the order rows first appear', () => {
    const rows = [line({ segment: 'dealer' }), line({ segment: 'project' })];
    expect(presentChannels(rows)).toEqual(['project', 'retail']);
  });
  it('never grows a third column, whatever the segments say', () => {
    expect(presentChannels([line({ segment: 'dealer' })])).toEqual(['retail']);
    expect(
      presentChannels([line({ segment: 'dealer' }), line({ segment: null })]),
    ).toEqual(['retail']);
  });
});

describe('groupPlanLinesByChannel - the TPE-9204 case (one row per PRODUCT)', () => {
  // 1 bare-site (dealer/Retail) row + 2 suffixed-bin (project) rows for the same product -
  // the captain's own complaint: "my expectation is 1 line of retail, 1 line of project" is
  // now satisfied INSIDE one product row via channel columns, not by a row per channel.
  const retail = line({
    id: 'a', warehouse_id: 'w-brw', warehouse_code: 'BRW', warehouse_name: 'Butterworth',
    segment: 'dealer', rank: 1, on_hand: 4, project_on_hand: 0, incoming_spo: 1, outstanding_po: 0,
    outstanding_sales: 6, order_qty: 3, net_position: -3, forecast_daily_demand: 1,
    retail_committed: 6, project_committed: 0, project_need: 0,
  });
  const projectIb = line({
    id: 'b', warehouse_id: 'w-ib', warehouse_code: 'BRW-IB', warehouse_name: 'BRW - IB',
    segment: 'project', rank: 2, on_hand: 2, project_on_hand: 3, incoming_spo: 0, outstanding_po: 1,
    outstanding_sales: 5, order_qty: 4, net_position: -4, forecast_daily_demand: 2,
    retail_committed: 0, project_committed: 5, project_need: 3,
  });
  const projectIr = line({
    id: 'c', warehouse_id: 'w-ir', warehouse_code: 'BRW-IR', warehouse_name: 'BRW - IR',
    segment: 'project', rank: 4, on_hand: 1, project_on_hand: 1, incoming_spo: 0, outstanding_po: 0,
    outstanding_sales: 2, order_qty: 5, net_position: -5, forecast_daily_demand: 1,
    retail_committed: 0, project_committed: 2, project_need: 1,
  });

  it('collapses all 3 per-warehouse rows of the same product into ONE grouped row', () => {
    const groups = groupPlanLinesByChannel([retail, projectIb, projectIr]);
    expect(groups).toHaveLength(1);
    expect(groups[0].sku).toBe('TPE-9204');
    expect(isGroupedLine(groups[0])).toBe(true);
  });

  it('the location label/title carries all 3 warehouses (<=3, so joined not counted)', () => {
    const [group] = groupPlanLinesByChannel([retail, projectIb, projectIr]);
    expect(group.__group.locationCodes).toEqual(['Butterworth', 'BRW - IB', 'BRW - IR']);
    expect(group.warehouse).toBe('Butterworth, BRW - IB, BRW - IR');
  });

  it('the channel columns are dynamic - Project and Retail, and never a third', () => {
    const [group] = groupPlanLinesByChannel([retail, projectIb, projectIr]);
    expect(group.__group.channels).toEqual(['project', 'retail']);
  });

  it("channelQty.project/.retail sum committed_v's split across the product's locations", () => {
    const [group] = groupPlanLinesByChannel([retail, projectIb, projectIr]);
    expect(group.__group.channelQty.project).toBe(7); // 0 + 5 + 2
    expect(group.__group.channelQty.retail).toBe(6); // 6 + 0 + 0
  });

  it('the channel sums equal the committed split sums across every member', () => {
    const [group] = groupPlanLinesByChannel([retail, projectIb, projectIr]);
    const expectedProject = [retail, projectIb, projectIr]
      .reduce((t, l) => t + (l.rec.project_committed ?? 0), 0);
    const expectedRetail = [retail, projectIb, projectIr]
      .reduce((t, l) => t + (l.rec.retail_committed ?? 0), 0);
    expect(group.__group.channelQty.project).toBe(expectedProject);
    expect(group.__group.channelQty.retail).toBe(expectedRetail);
  });

  it('projectConfirmedQty sums the confirmed-for-buy subset (project_need), not channelQty.project', () => {
    const [group] = groupPlanLinesByChannel([retail, projectIb, projectIr]);
    expect(group.__group.projectConfirmedQty).toBe(4); // 0 + 3 + 1
    expect(group.__group.projectConfirmedQty).not.toBe(group.__group.channelQty.project);
  });

  it('sums the shared numeric facts across the group\'s warehouses', () => {
    const [group] = groupPlanLinesByChannel([retail, projectIb, projectIr]);
    expect(group.rec.on_hand).toBe(7); // 4 + 2 + 1
    // Pool-only supply (`on_hand`) and project-held supply (`project_on_hand`) are two
    // separate sums of two separate per-location facts (captain, 20 Aug) - summing the
    // group never mixes the two back together.
    expect(group.rec.project_on_hand).toBe(4); // 0 + 3 + 1
    expect(group.rec.incoming_spo).toBe(1);
    expect(group.rec.outstanding_po).toBe(1);
    expect(group.rec.outstanding_sales).toBe(13); // 6 + 5 + 2
    expect(group.order_qty).toBe(12); // 3 + 4 + 5
    expect(group.net).toBe(-12); // -3 + -4 + -5
    expect(group.forecast_daily_demand).toBe(4); // 1 + 2 + 1
    // Runway recomputed from the summed net/forecast, not averaged per-location ratios.
    expect(group.days_cover).toBe(-3);
  });

  it('takes the MINIMUM member priority for the group', () => {
    const [group] = groupPlanLinesByChannel([retail, projectIb, projectIr]);
    expect(group.rankOrder).toBe(1); // min(1, 2, 4)
  });

  it('keeps the members reachable for the expand drill, in their original order', () => {
    const [group] = groupPlanLinesByChannel([retail, projectIb, projectIr]);
    expect(group.__group.members).toEqual([retail, projectIb, projectIr]);
  });

  it('is flagged by isGroupedLine, and an ungrouped line is not', () => {
    const [group] = groupPlanLinesByChannel([retail]);
    expect(isGroupedLine(group)).toBe(true);
    expect(isGroupedLine(retail)).toBe(false);
  });

  it('carries a single member\'s own price/supplier straight through - a lone group has nothing to conflict with (captain, 20 Aug: product facts, not per-location)', () => {
    const [group] = groupPlanLinesByChannel([retail]);
    expect(group.unit_cost).toBe(10);
    expect(group.supplier.code).toBe('S1');
    expect(group.rec.unit_cost).toBe(10);
  });

  it('preserves a null shared fact as null rather than reading it as zero', () => {
    const noSpo = line({ id: 'e', incoming_spo: null, rank: 6 });
    const noSpo2 = line({ id: 'f', incoming_spo: null, rank: 7, warehouse_id: 'w-x2' });
    const [group] = groupPlanLinesByChannel([noSpo, noSpo2]);
    expect(group.rec.incoming_spo).toBeNull();
  });

  it('preserves a null channelQty entry rather than reading a legacy plan as zero', () => {
    const legacy = line({
      id: 'g', warehouse_id: 'w-legacy', rank: 8,
      project_committed: null, retail_committed: null,
    });
    const [group] = groupPlanLinesByChannel([legacy]);
    expect(group.__group.channelQty.project).toBeNull();
    expect(group.__group.channelQty.retail).toBeNull();
  });

  it('groups a segment-less warehouse into the SAME product row, as retail', () => {
    const untagged = line({
      id: 'd', warehouse_id: 'w-x', warehouse_code: 'WHX', warehouse_name: 'Unmapped',
      segment: null, rank: 5, outstanding_sales: 1, retail_committed: 1,
    });
    const groups = groupPlanLinesByChannel([retail, untagged]);
    expect(groups).toHaveLength(1);
    expect(groups[0].__group.members).toEqual([retail, untagged]);
    expect(groups[0].__group.channels).toEqual(['retail']);
    expect(groups[0].__group.channelQty.retail).toBe(7);
  });

  it('carries the master reorder level/qty through from the first member (19-20 Aug follow-up)', () => {
    const withMaster = line({
      id: 'h', warehouse_id: 'w-master', rank: 9,
      master_reorder_level: 10, master_reorder_quantity: 50,
    });
    const [group] = groupPlanLinesByChannel([withMaster]);
    expect(group.rec.master_reorder_level).toBe(10);
    expect(group.rec.master_reorder_quantity).toBe(50);
  });

  it('leaves the master reorder level/qty null rather than 0/undefined when no member carries one', () => {
    const [group] = groupPlanLinesByChannel([retail]);
    expect(group.rec.master_reorder_level).toBeNull();
    expect(group.rec.master_reorder_quantity).toBeNull();
  });

  it('groups a second product separately even when it shares a channel', () => {
    const other = line({
      id: 'g', product_id: 'p2', sku: 'OTHER-1', product_name: 'Other product',
      segment: 'dealer', rank: 3,
    });
    const groups = groupPlanLinesByChannel([retail, other]);
    expect(groups).toHaveLength(2);
    expect(groups.map((g) => g.sku)).toEqual(['TPE-9204', 'OTHER-1']);
    // Each product's own members stay isolated - no cross-product bleed into either sum.
    expect(groups[0].__group.members).toEqual([retail]);
    expect(groups[1].__group.members).toEqual([other]);
  });
});

describe('supplier/price/MOQ are product facts (captain, 20 Aug ruling): carried when uniform, dashed on conflict', () => {
  // Same product, same supplier/price/MOQ on every member - verified on the live run to be
  // the overwhelmingly common case (see the file header). `cash_impact` is scaled with
  // `order_qty` so the derived `unit_cost_base` (cash_impact / order_qty) also lands on the
  // same figure for both members, isolating the assertion to the carry-through rule itself.
  const uniformA = line({ id: 'u1', warehouse_id: 'w-u1', rank: 20, order_qty: 5, cash_impact: 50, moq: 50 });
  const uniformB = line({ id: 'u2', warehouse_id: 'w-u2', rank: 21, order_qty: 8, cash_impact: 80, moq: 50 });

  it('carries supplier/price/MOQ through onto the group row when every member agrees', () => {
    const [group] = groupPlanLinesByChannel([uniformA, uniformB]);
    expect(group.unit_cost).toBe(10);
    expect(group.unit_cost_base).toBe(10);
    expect(group.rec.unit_cost).toBe(10);
    expect(group.supplier.code).toBe('S1');
    expect(group.rec.supplier?.supplier_code).toBe('S1');
    expect(group.order_qty_inputs.moq).toBe(50);
    expect(group.rec.moq).toBe(50);
  });

  it('a single-member group carries that one member\'s facts through the same way', () => {
    const [group] = groupPlanLinesByChannel([uniformA]);
    expect(group.unit_cost).toBe(10);
    expect(group.supplier.code).toBe('S1');
    expect(group.order_qty_inputs.moq).toBe(50);
  });

  it('falls back to null / no-supplier on a genuine conflict, never inventing a figure', () => {
    const conflicting = line({
      id: 'u3', warehouse_id: 'w-u3', rank: 22, order_qty: 5, cash_impact: 100, moq: 80,
      supplier: {
        supplier_code: 'S2', supplier_name: 'Other Co', unit_cost: 20,
        lead_time_days: 10, composite_score: 0, is_primary: false,
      },
      unit_cost: 20,
    });
    const [group] = groupPlanLinesByChannel([uniformA, conflicting]);
    expect(group.unit_cost).toBeNull();
    expect(group.unit_cost_base).toBeNull();
    expect(group.rec.unit_cost).toBeNull();
    expect(group.supplier.code).toBe('');
    expect(group.rec.supplier).toBeNull();
    expect(group.order_qty_inputs.moq).toBeNull();
    expect(group.rec.moq).toBeNull();
  });
});
