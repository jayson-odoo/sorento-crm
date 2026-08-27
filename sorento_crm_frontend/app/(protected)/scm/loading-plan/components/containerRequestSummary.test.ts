import { describe, it, expect } from 'vitest';

import { summariseContainerRequest } from './containerRequestSummary';
import type { ContainerRequestRow } from '../../services/fulfilmentService';

function row(over: Partial<ContainerRequestRow> = {}): ContainerRequestRow {
  const merged: ContainerRequestRow = {
    // F12: an ordinary product row. A set row sets `row_kind`, `product_set_id` and the
    // driver fields; `row_key` follows `product_id` unless a test names its own.
    row_key: 'p1',
    row_kind: 'product' as const,
    product_set_id: null,
    set_code: null,
    set_name: null,
    driver_product_id: null,
    driver_item_code: null,
    driver_product_name: null,
    product_id: 'p1',
    item_code: 'ITEM-1',
    product_name: 'Widget',
    open_so_need: 0,
    suggested_qty: 0,
    on_hand: 0,
    on_hand_group: 0,
    incoming_spo: 0,
    incoming_spo_group: 0,
    incoming_pl: 0,
    incoming_pl_shipments: [],
    outstanding_po: 0,
    outstanding_po_lines: [],
    sites: [],
    group_locations: { count: 0, on_hand: 0, incoming_spo: 0, warehouse_codes: [] },
    project_qty: 0,
    retail_qty: 0,
    unclassified_qty: 0,
    earliest_required_date: null,
    so_count: 0,
    holding_source: 'stock_list',
    holding_qty: 0,
    holding_as_of: null,
    qty_packed: 0,
    qty_unfinished: 0,
    cbm_per_unit: null,
    row_as_of: null,
    rank: 1,
    rank_score: 0.5,
    rank_factors: [],
    has_demand: true,
    ...over,
  };
  // Keyed off whatever `product_id` ended up being, so two rows in one test never collide
  // on the grid's row id just because only one of them named a key.
  return { ...merged, row_key: over.row_key ?? merged.product_id };
}

const asked = (r: ContainerRequestRow) => r.suggested_qty;

describe('summariseContainerRequest', () => {
  it('decomposes the need: pool stock first, then SPO, then the ask', () => {
    const rows = [
      row({ product_id: 'a', open_so_need: 100, on_hand: 30, incoming_spo: 20, suggested_qty: 50 }),
      row({ product_id: 'b', open_so_need: 40, on_hand: 0, incoming_spo: 0, suggested_qty: 40 }),
    ];

    const s = summariseContainerRequest(rows, asked);

    expect(s.need).toBe(140);
    expect(s.fromPool).toBe(30);
    expect(s.fromSpo).toBe(20);
    expect(s.toAsk).toBe(90);
    // The three parts foot back to the need, which is the whole reason they are cards and
    // not column totals.
    expect(s.fromPool + s.fromSpo + s.toAsk).toBe(s.need);
  });

  it('never counts more cover than there is need for it', () => {
    // 1.3 million units of BRW stock against a need of 40 is not "1.3 million covered".
    const rows = [row({ open_so_need: 40, on_hand: 1_300_000, incoming_spo: 900, suggested_qty: 0 })];

    const s = summariseContainerRequest(rows, asked);

    expect(s.fromPool).toBe(40);
    expect(s.fromSpo).toBe(0);
    expect(s.toAsk).toBe(0);
  });

  it('follows the edited quantity, not the suggestion', () => {
    const rows = [row({ open_so_need: 100, suggested_qty: 100, qty_packed: 60, holding_qty: 60 })];

    const s = summariseContainerRequest(rows, () => 25);

    expect(s.toAsk).toBe(25);
    // Of what is being asked for, this much is already packed.
    expect(s.canPackNow).toBe(25);
  });

  it('caps what they can pack now at what they actually hold packed', () => {
    const rows = [row({ open_so_need: 100, suggested_qty: 100, qty_packed: 12, holding_qty: 12 })];

    expect(summariseContainerRequest(rows, asked).canPackNow).toBe(12);
  });

  it('estimates the volume of the ask and counts the products it cannot measure', () => {
    const rows = [
      row({ product_id: 'a', suggested_qty: 100, cbm_per_unit: 0.05 }),
      row({ product_id: 'b', suggested_qty: 10, cbm_per_unit: null }),
      // Not asked for, so its cbm is not part of this container's estimate.
      row({ product_id: 'c', suggested_qty: 0, cbm_per_unit: null }),
    ];

    const s = summariseContainerRequest(rows, asked);

    expect(s.askCbm).toBeCloseTo(5);
    expect(s.askCbmUnmeasured).toBe(1);
  });
});

describe('summariseContainerRequest - what the supplier can pack today', () => {
  it('counts the packed figure on a stock-list row', () => {
    const out = summariseContainerRequest(
      [row({ suggested_qty: 500, holding_source: 'stock_list', holding_qty: 120, qty_packed: 120 })],
      asked,
    );

    expect(out.canPackNow).toBe(120);
  });

  it('counts the invoiced quantity on a proforma row, not the zeroed packed field', () => {
    // The backend zeroes `qty_packed` on a proforma-sourced row: a proforma states one
    // quantity per line and there is no packed/unfinished split to report. Reading that
    // field made the card say 0 while the grid beside it said 400.
    const out = summariseContainerRequest(
      [
        row({
          suggested_qty: 500,
          holding_source: 'proforma',
          holding_qty: 400,
          qty_packed: 0,
          qty_unfinished: 0,
        }),
      ],
      asked,
    );

    expect(out.canPackNow).toBe(400);
  });

  it('counts nothing when neither document names the product', () => {
    const out = summariseContainerRequest(
      [row({ suggested_qty: 500, holding_source: 'none', holding_qty: null, qty_packed: 0 })],
      asked,
    );

    expect(out.canPackNow).toBe(0);
  });
});
