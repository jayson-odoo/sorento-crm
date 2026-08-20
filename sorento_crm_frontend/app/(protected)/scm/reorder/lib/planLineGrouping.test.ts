/**
 * Product-grain channel grouping (5.3): "1 line of retail, 1 line of project" per product,
 * reproducing the captain's TPE-9204 complaint (one bare-site Retail row + two suffixed-bin
 * Project rows collapsing into two grouped rows, not staying three).
 */
import { describe, it, expect } from 'vitest';
import type { ReorderRecommendation } from '../types/reorder.types';
import { recToPlanLine, type PlanLine } from './planLine';
import {
  channelOf,
  groupPlanLinesByChannel,
  isGroupedLine,
  locationLabel,
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
  it('is Unclassified rather than guessed at when the segment is missing', () => {
    expect(channelOf(line({ segment: null }))).toBe('unclassified');
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

describe('groupPlanLinesByChannel - the TPE-9204 case', () => {
  // 1 bare-site (dealer/Retail) row + 2 suffixed-bin (project) rows for the same product.
  const retail = line({
    id: 'a', warehouse_id: 'w-brw', warehouse_code: 'BRW', warehouse_name: 'Butterworth',
    segment: 'dealer', rank: 1, on_hand: 4, incoming_spo: 1, outstanding_po: 0,
    outstanding_sales: 6, order_qty: 3, net_position: -3, forecast_daily_demand: 1,
  });
  const projectIb = line({
    id: 'b', warehouse_id: 'w-ib', warehouse_code: 'BRW-IB', warehouse_name: 'BRW - IB',
    segment: 'project', rank: 2, on_hand: 2, incoming_spo: 0, outstanding_po: 1,
    outstanding_sales: 5, order_qty: 4, net_position: -4, forecast_daily_demand: 2,
  });
  const projectIr = line({
    id: 'c', warehouse_id: 'w-ir', warehouse_code: 'BRW-IR', warehouse_name: 'BRW - IR',
    segment: 'project', rank: 4, on_hand: 1, incoming_spo: 0, outstanding_po: 0,
    outstanding_sales: 2, order_qty: 5, net_position: -5, forecast_daily_demand: 1,
  });

  it('collapses 3 per-warehouse rows into 2 - one Retail, one Project', () => {
    const groups = groupPlanLinesByChannel([retail, projectIb, projectIr]);
    expect(groups).toHaveLength(2);
    expect(groups.map((g) => g.__group.channel)).toEqual(['retail', 'project']);
  });

  it('the Retail group has 1 location and the Project group has 2', () => {
    const [retailGroup, projectGroup] = groupPlanLinesByChannel([retail, projectIb, projectIr]);
    expect(retailGroup.__group.locationCodes).toEqual(['Butterworth']);
    expect(projectGroup.__group.locationCodes).toEqual(['BRW - IB', 'BRW - IR']);
    expect(projectGroup.warehouse).toBe('BRW - IB, BRW - IR');
  });

  it('sums the shared numeric facts across the group\'s warehouses', () => {
    const [, projectGroup] = groupPlanLinesByChannel([retail, projectIb, projectIr]);
    expect(projectGroup.rec.on_hand).toBe(3); // 2 + 1
    expect(projectGroup.rec.incoming_spo).toBe(0);
    expect(projectGroup.rec.outstanding_po).toBe(1);
    expect(projectGroup.rec.outstanding_sales).toBe(7); // 5 + 2
    expect(projectGroup.order_qty).toBe(9); // 4 + 5
    expect(projectGroup.net).toBe(-9); // -4 + -5
    expect(projectGroup.forecast_daily_demand).toBe(3); // 2 + 1
    // Runway recomputed from the summed net/forecast, not averaged per-location ratios.
    expect(projectGroup.days_cover).toBe(-3);
  });

  it('takes the MINIMUM member priority for the group', () => {
    const [retailGroup, projectGroup] = groupPlanLinesByChannel([retail, projectIb, projectIr]);
    expect(retailGroup.rankOrder).toBe(1);
    expect(projectGroup.rankOrder).toBe(2); // min(2, 4)
  });

  it('keeps the members reachable for the expand drill', () => {
    const [, projectGroup] = groupPlanLinesByChannel([retail, projectIb, projectIr]);
    expect(projectGroup.__group.members).toEqual([projectIb, projectIr]);
  });

  it('is flagged by isGroupedLine, and an ungrouped line is not', () => {
    const [retailGroup] = groupPlanLinesByChannel([retail]);
    expect(isGroupedLine(retailGroup)).toBe(true);
    expect(isGroupedLine(retail)).toBe(false);
  });

  it('never sums a price - a group row has no opinion on cost', () => {
    const [retailGroup] = groupPlanLinesByChannel([retail]);
    expect(retailGroup.unit_cost).toBeNull();
    expect(retailGroup.unit_cost_base).toBeNull();
    expect(retailGroup.rec.unit_cost).toBeNull();
  });

  it('an unclassified-segment line groups on its own line, not folded into Retail', () => {
    const unclassified = line({
      id: 'd', warehouse_id: 'w-x', warehouse_code: 'WHX', warehouse_name: 'Unmapped',
      segment: null, rank: 5, outstanding_sales: 1,
    });
    const groups = groupPlanLinesByChannel([retail, unclassified]);
    expect(groups).toHaveLength(2);
    const unclassifiedGroup = groups.find((g) => g.__group.channel === 'unclassified');
    expect(unclassifiedGroup).toBeDefined();
    expect(unclassifiedGroup?.__group.members).toEqual([unclassified]);
  });

  it('preserves a null shared fact as null rather than reading it as zero', () => {
    const noSpo = line({ id: 'e', incoming_spo: null, rank: 6 });
    const noSpo2 = line({ id: 'f', incoming_spo: null, rank: 7, warehouse_id: 'w-x2' });
    const [group] = groupPlanLinesByChannel([noSpo, noSpo2]);
    expect(group.rec.incoming_spo).toBeNull();
  });

  it('groups a second product separately even in the same channel', () => {
    const other = line({
      id: 'g', product_id: 'p2', sku: 'OTHER-1', product_name: 'Other product',
      segment: 'dealer', rank: 3,
    });
    const groups = groupPlanLinesByChannel([retail, other]);
    expect(groups).toHaveLength(2);
    expect(groups.map((g) => g.sku)).toEqual(['TPE-9204', 'OTHER-1']);
  });
});
