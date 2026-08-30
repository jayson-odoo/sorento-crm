/**
 * Stock Debt - the field-for-field payload contract (S2, AC-S2-6 / AC-S2-7).
 *
 * `services/stockDebtService.ts` carries the ROUTE contract (paths, params, auth); this
 * file carries the SHAPES, so neither restates the other. Both the Phase-1 fixture and
 * the Phase-2 backend answer to exactly these types.
 */

/** Where a month's balance sits against "can this still be bought in time" (AC-S2-6). */
export type StockDebtTone = 'red' | 'amber' | 'green';

/** One month cell of a product row. `balance` is the CUMULATIVE dated running balance. */
export interface StockDebtMonth {
  /** `YYYY-MM`. Always one of the axis keys in `StockDebtListResponse.months`. */
  key: string;
  balance: number;
  tone: StockDebtTone;
}

/**
 * One product's debt row.
 *
 * `product_id` exists only to address the cell route - it is NEVER rendered (cursor rule:
 * no UUIDs in the UI). The reader sees `product_code` and `product_name`.
 */
export interface StockDebtRow {
  product_id: string;
  product_code: string;
  product_name: string | null;
  /** One entry per axis month, in axis order. */
  months: StockDebtMonth[];
  /** Total demand dated on or after the policy's `tba_date_from`. Draws no supply (R14). */
  tba: number;
  /** Total demand with no required date. Draws no supply (R14). */
  undated: number;
  /**
   * Total demand booked at NO warehouse. In no ownership group's pile, so it draws
   * nothing - and it is counted rather than dropped, because a screen that lists what is
   * owed and silently omits it answers a narrower question than the one it is asked.
   */
  unlocated: number;
}

/** The list envelope: the repo's standard `{data, pagination}` plus the column axis. */
export interface StockDebtListResponse {
  data: StockDebtRow[];
  pagination: { total: number; page: number; limit: number };
  /**
   * The month columns, current month -> last dated month carrying demand or supply.
   *
   * Server-declared rather than derived from the page's rows: the axis is a property of
   * the WHOLE filtered set, so deriving it per page would make the columns change under
   * the reader as they page.
   */
  months: string[];
  /** `YYYY-MM` of the policy's `tba_date_from` - the TBA column's own label. */
  tba_month: string;
  /** Ownership groups the flag currently admits, for the toolbar's select. */
  groups: string[];
}

/** How a demand line ended up in a cell (AC-S2-7). */
export type StockDebtDemandStatus = 'covered' | 'late' | 'short' | 'pinned';

/** One sales-order line due in the cell's month (or in its TBA / undated bucket). */
export interface StockDebtDemandLine {
  so_number: string;
  agent_code: string | null;
  /** The bin the line is booked in - the drill's Bin column. Null for an unlocated line. */
  warehouse_code: string | null;
  /** `YYYY-MM-DD`, or null for an undated line. */
  required_date: string | null;
  open_qty: number;
  assigned_qty: number;
  /** Human source of the assignment: `On hand DC1-BB`, `SPO 2026/08-0063`, `PO ... line 3`. */
  assigned_source: string | null;
  status: StockDebtDemandStatus;
}

/** What a supply event is: stock already held, a shipment arriving, or a PO on order. */
export type StockDebtSupplyKind = 'on_hand' | 'spo' | 'po';

/** One supply event landing in the cell's month (AC-S2-7). */
export interface StockDebtSupplyEvent {
  kind: StockDebtSupplyKind;
  /** Document reference. Null for on hand, which is a bin rather than a document. */
  ref: string | null;
  warehouse_code: string | null;
  /** Arrival: today for on hand, the SPO's arrival, `issue + lead` for a PO line (R29). */
  date: string | null;
  /** PO only: the SO delivery date the line was typed against. Display only (R30). */
  bought_for: string | null;
  qty: number;
  /** Arrival passed with nothing received: listed, but counted as nothing (R31). */
  overdue: boolean;
  assigned_to: { so_number: string; qty: number }[];
}

/** The cell drill (R28): the two tables behind one product x month. */
export interface StockDebtCell {
  demand: StockDebtDemandLine[];
  supply: StockDebtSupplyEvent[];
}
