/**
 * The SPO investigation grid (PLAN-spo-investigation-grid.md): a DOCUMENT read of
 * `spo_allocations`, grouped by `spo_number` at read time. No new table - `spo_documents`
 * stays out of scope (plan's "Not in scope").
 *
 * Every computed field here (`balance`, `arrival_date`, `overdue_days`, `planning_span`,
 * the header rollups) is owed to `app.services.scm.spo_supply.open_incoming_clauses()` in
 * Phase 2 - the fifth reader of that ONE rule, never a restated copy. Phase 1 (this file +
 * `services/spoDocumentService.ts`) mocks the shape so the screen can be built and reviewed
 * before that wiring lands.
 */

/** The three states the document list's tabs read: All / Outstanding (default) / Completed. */
export type SPODocumentState = 'all' | 'outstanding' | 'completed';

/** Whether fulfilment planning can see this line (plan Q4, UAC AC-6). */
export type PlanningSpan = 'in_plan' | 'pool' | 'off' | 'none';

/** One SPO number's header row, as the document list renders it (UAC AC-2). */
export interface SPODocumentRow {
  /** The document's own key - also `id`, so the row satisfies `useListPager`'s
   *  `{id: string}` contract without a second field meaning the same thing. */
  id: string;
  spo_number: string;
  /** Earliest line `created_at` on the document. */
  doc_date: string | null;
  /** The majority supplier across the document's lines. */
  supplier_name: string | null;
  /** How many OTHER suppliers disagree with `supplier_name` (Q8) - 0 when every line
   *  agrees, so the "+N more" chip renders only where the data actually disagrees. */
  supplier_extra_count: number;
  status: 'outstanding' | 'completed';
  /** Earliest ETA across the document's lines, AS IS - no TBA masking (Q3). */
  earliest_eta: string | null;
  total_allocated: number;
  total_received: number;
  /** Sum of `balance` over OUTSTANDING lines only. */
  balance: number;
  line_count: number;
  /** Max `overdue_days` over the document's OUTSTANDING lines; 0 when none are late. */
  worst_overdue_days: number;
}

/** One allocation line, with the computed fields the Lines tab renders (UAC AC-6, AC-13). */
export interface SPODocumentLine {
  id: string;
  spo_number: string | null;
  product_id: string | null;
  product: { id: string; product_code: string; product_name: string } | null;
  warehouse_id: string | null;
  warehouse: { id: string; warehouse_code: string; warehouse_name: string } | null;
  allocated_quantity: number;
  quantity_received: number;
  quantity_rejected: number;
  /** `max(allocated - received, 0)`. */
  balance: number;
  /** The one coalesce: shipment `eta_delay_date` -> shipment `estimated_arrival_date` ->
   *  line `expected_date`. Rendered AS IS - no TBA masking of a 2029/2030 placeholder. */
  arrival_date: string | null;
  /** `spo_supply.overdue_days` - 0 when not late, unstated, or the line is not open. */
  overdue_days: number;
  /** Shipment supplier when a shipment is booked, else the line's own supplier. */
  supplier_name: string | null;
  planning_span: PlanningSpan;
  receipt_status: string;
  /** Whether this line still counts as incoming supply (`open_incoming_clauses` + balance
   *  > 0). Drives the Outstanding/Completed rollup and the list's row-membership filter. */
  outstanding: boolean;
  inbound_shipment: {
    id: string;
    shipment_number: string | null;
    shipping_container_number?: string | null;
  } | null;
  line_status?: string | null;
}

/** The document form view's payload: header rollup + every line (UAC AC-6). */
export interface SPODocument {
  spo_number: string;
  doc_date: string | null;
  supplier_name: string | null;
  supplier_extra_count: number;
  status: 'outstanding' | 'completed';
  total_allocated: number;
  total_received: number;
  balance: number;
  line_count: number;
  lines: SPODocumentLine[];
}

/** The document list's filters, matching the Phase 2 endpoint's own query params
 *  (plan S1: `state`, `product_id`, `warehouse_id`, `overdue_only`, `query`). */
export interface SPODocumentListFilters {
  state?: SPODocumentState;
  product_id?: string | null;
  warehouse_id?: string | null;
  overdue_only?: boolean | null;
}
