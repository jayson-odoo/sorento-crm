/**
 * SCM M4 Slice B - human decision layer types (Accept / Adjust / Reject) +
 * the draft→confirm PO flow they feed. These are the FE contract for the
 * Phase-2 endpoints documented at the top of `services/decisionService.ts`.
 *
 * A decision is tracked SEPARATELY from the frozen `ReorderRecommendation`
 * (M4-D7: the recommendation is never mutated - an Accept/Adjust writes an
 * append-only override server-side). The view keys decisions by recommendation
 * id and renders the resulting status badge + which draft PO the accept landed
 * in.
 */

/** Where a recommendation sits in the human review loop.
 *  `proposed` = untouched; the others are the three terminal decisions. */
export type RecDecisionStatus = 'proposed' | 'accepted' | 'adjusted' | 'dismissed';

/** The decision recorded against one recommendation. Adjusted rows carry the
 *  qty/supplier override + reason; dismissed rows carry the reject reason. */
export interface RecDecision {
  recommendation_id: string;
  status: RecDecisionStatus;
  /** Overridden buy qty (adjust only); null when accepted as-proposed / rejected. */
  override_qty: number | null;
  /** Switched supplier code (adjust only); null when the proposed supplier stands. */
  override_supplier_code: string | null;
  /** Human supplier name for display (no code shown raw). */
  override_supplier_name: string | null;
  /** Raw reason text (adjust + reject). Classified into a code in Slice C - not here. */
  reason_text: string | null;
  /** The draft PO this accept/adjust consolidated into (human PO number, never a UUID).
   *  Reflects the CURRENT number - after Confirm renumbers a draft to PO-YYYY-####. */
  draft_po_number: string | null;
  /** Stable PO id the number resolves to - powers the "→ PO" detail hyperlink. */
  draft_po_id: string | null;
}

/** Adjust modal submission (M4-D7). */
export interface AdjustPayload {
  override_qty: number;
  /** null = keep the proposed supplier. */
  override_supplier_code: string | null;
  reason_text: string;
}

/** Reject dialog submission (M4-D8). Reason is required. */
export interface RejectPayload {
  reason_text: string;
}

/** Result of a single Accept/Adjust. Decisions are STAGED - no PO exists until
 *  Confirm decisions - so the PO fields are null here (populated later via the
 *  decisions read once confirmed). `supplier_name` drives the toast. */
export interface AcceptResult {
  draft_po_number: string | null;
  draft_po_id: string | null;
  supplier_name: string;
}

/** Result of a bulk Accept-funded run (M4-D9) - staged, so `po_count` is 0. */
export interface BulkAcceptResult {
  accepted_count: number;
  po_count: number;
}

/** Result of Confirm decisions (M4-D4) - how many staged decisions materialised
 *  and how many consolidated draft POs were created / updated (one per supplier). */
export interface ConfirmDecisionsResult {
  confirmed_count: number;
  po_count: number;
}

/**
 * S16 (captain, 21 Aug, 3rd time requested): the row decision - buy / use stock /
 * use PO / skip, or a mixture - recorded directly on a plan row. Mirrors the backend
 * schemas at `app/schemas/scm_decisions.py` (`RecordPlanRowDecisionRequest` /
 * `PlanRowDecision`). `mixture` is the ONLY value not in `PlanDecisionKind`
 * (`lib/planDecisions.ts`) - that FE type never needed a fifth choice, because a
 * mixture is one decision carrying several parts, not a separate branch; the kind
 * sent to the backend is DERIVED from those parts (`planDecisionKind`).
 */
export type PlanRowDecisionKind = 'buy' | 'use_stock' | 'use_po' | 'skip' | 'mixture';

/** One bin the buyer is drawing stock from. Location is a warehouse CODE - never a
 *  UUID from the UI. */
export interface StockTakeIn {
  location: string;
  qty: number;
}

/** The server's own echo of a stock take, with the human location name alongside
 *  the code it was recorded against. */
export interface StockTakeOut {
  location: string;
  location_name: string | null;
  qty: number;
}

/** How the row is costed: what we last paid, or a price still to be asked for. */
export type PlanRowPriceMode = 'use_last' | 'ask_new';

/** Body of `POST .../recommendations/{rec_id}/decision`. */
export interface RecordPlanRowDecisionPayload {
  kind: PlanRowDecisionKind;
  buy_qty?: number;
  stock_takes?: StockTakeIn[];
  po_qty?: number;
  po_refs?: string[];
  reason_text?: string;
  /** AC-R13 / AC-R14. The supplier travels as a CODE - no UUID crosses the wire. The
   *  backend re-reads that supplier's last price itself, so no price is sent. */
  price_mode?: PlanRowPriceMode;
  supplier_code?: string;
}

/** The persisted row decision, as the backend returns it (record, clear-idempotent
 *  read, and the run-wide list). */
export interface PlanRowDecision {
  recommendation_id: string;
  kind: PlanRowDecisionKind;
  buy_qty: number | null;
  stock_takes: StockTakeOut[];
  po_qty: number | null;
  po_refs: string[];
  reason_text: string | null;
  /** The buyer's price call. `use_last` on a decision that never made one. */
  price_mode: PlanRowPriceMode;
  /** The supplier the BUYER chose, when they overrode the engine's. Null = the
   *  recommendation's own proposed supplier stands. */
  supplier_code: string | null;
  supplier_name: string | null;
  /** What the row is costed at. Null under `ask_new` - not a price of zero. */
  unit_cost: number | null;
  lead_time_days: number | null;
  /** Staged like Accept/Adjust - populated only once Confirm decisions has drafted
   *  the buy portion into a PO. Null until then. */
  draft_po_number: string | null;
  draft_po_id: string | null;
}

/** `GET .../reorder-runs/{run_id}/plan-row-decisions`. */
export interface PlanRowDecisionListResponse {
  data: PlanRowDecision[];
  /** The results-grid header's ("N of Total made") numerator/denominator, counted
   *  server-side off what is actually persisted - never off client session state. */
  decided_count: number;
  total_count: number;
}
