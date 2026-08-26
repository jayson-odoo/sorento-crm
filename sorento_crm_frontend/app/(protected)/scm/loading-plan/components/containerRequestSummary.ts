import type { ContainerRequestRow } from '../../services/fulfilmentService';

/**
 * The five figures above the loading-plan grid (PLAN section 2b, AC-A2.1).
 *
 * They DECOMPOSE the need rather than restate the columns: need is covered first by what the
 * site pools already hold, then by what is on the water, and what is left is the ask. Summing
 * the columns instead would put 1.3 million units of BRW stock on a card next to a 61,802
 * need, which says nothing about this container.
 *
 * `toAsk` follows the editable cell, not `suggested_qty`, because the card has to move when
 * she overrides a quantity - that is the whole reason it is above the grid.
 */
export interface ContainerRequestSummary {
  /** Gross open SO need over every row. */
  need: number;
  /** Of that need, the part the site pools already hold. */
  fromPool: number;
  /** Of what the pools do not hold, the part already on the water as an SPO. */
  fromSpo: number;
  /** What is actually being asked for, her edits included. */
  toAsk: number;
  /** Estimated volume of the ask, from the stock list's own per-unit cbm. */
  askCbm: number;
  /** How many asked-for products state no per-unit cbm, so `askCbm` understates the load. */
  askCbmUnmeasured: number;
  /** Of the ask, what the supplier says is packed and could go now. */
  canPackNow: number;
}

export function summariseContainerRequest(
  rows: ContainerRequestRow[],
  qtyFor: (row: ContainerRequestRow) => number,
): ContainerRequestSummary {
  const summary: ContainerRequestSummary = {
    need: 0,
    fromPool: 0,
    fromSpo: 0,
    toAsk: 0,
    askCbm: 0,
    askCbmUnmeasured: 0,
    canPackNow: 0,
  };

  for (const row of rows) {
    const need = row.open_so_need;
    const pool = Math.min(row.on_hand, need);
    const spo = Math.min(Math.max(need - row.on_hand, 0), row.incoming_spo);
    const qty = qtyFor(row);

    summary.need += need;
    summary.fromPool += pool;
    summary.fromSpo += spo;
    summary.toAsk += qty;
    // Whatever their own latest statement says they have - the stock list's packed figure
    // or the stand-in proforma's quantity. `qty_packed` alone reads 0 on a proforma row (the
    // backend zeroes it: a proforma states one quantity and no packed/unfinished split), so
    // this card said 0 under a grid cell reading 400.
    summary.canPackNow += Math.min(qty, row.holding_qty ?? 0);
    if (qty > 0) {
      if (row.cbm_per_unit === null) summary.askCbmUnmeasured += 1;
      else summary.askCbm += qty * row.cbm_per_unit;
    }
  }

  return summary;
}
