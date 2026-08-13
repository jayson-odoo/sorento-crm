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
