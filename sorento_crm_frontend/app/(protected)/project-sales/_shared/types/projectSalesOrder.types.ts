/**
 * P7 and P11 wire shapes, transcribed from CONTRACT-project-lead-to-so.md sections 5 and 6.
 *
 * Money and quantities are decimal STRINGS on purpose and stay strings all the way to the
 * screen. A float round trip loses cents on a 1.8 million ringgit order, so nothing in this
 * slice parses them except the display and comparison helpers in SalesOrderMoney.tsx, which
 * work on the digits.
 *
 * Fields the contract does not promise are optional here, so a backend that has not shipped
 * them yet renders a stated absence rather than crashing.
 */

import type { ReviewState } from './fulfilmentPlanning.types';

export type SalesOrderStatus =
  | 'draft'
  | 'blocked'
  | 'ready'
  /** Sponsorship only (AC-K3): drafted at price zero, waiting on Accounts. Gates publish. */
  | 'awaiting_costing'
  | 'published'
  | 'amended';

/** Where the split came from. The split is a proposal, never a rule (AC-F4a). */
export type GroupingOrigin =
  | 'area'
  | 'learned'
  | 'manual'
  | 'subset'
  | 'delivery_date'
  | 'delivery_month';

/**
 * How the builder cuts the drafted lines into sales orders. Chosen per build: the schedule
 * area is the default because the schedule already names it, but a customer who orders
 * against dates rather than areas gets one order per delivery date or per month instead.
 */
export type SalesOrderSplitBy = 'area' | 'delivery_date' | 'delivery_month';

export type FindingSeverity = 'hard' | 'warn' | 'info';

/** The five hard stops, all arithmetic. Any unacknowledged one refuses publish. */
export const HARD_FINDING_CODES = [
  'line_arithmetic',
  'total_mismatch',
  'schedule_short',
  'schedule_over',
  'unresolved_product',
] as const;

export type HardFindingCode = (typeof HARD_FINDING_CODES)[number];

export const WARN_FINDING_CODES = [
  'price_vs_quotation',
  'code_vs_quotation',
  'missing_delivery_date',
  'phase_unmatched',
  'credit_exposure',
  'no_package_mapping',
  'pre_order_overlap',
] as const;

export type WarnFindingCode = (typeof WARN_FINDING_CODES)[number];

export type ExplosionSource = 'package' | 'quotation' | 'none';

/** Row of `GET /projects/{project_id}/sales-orders` (contract 5.2). */
export interface ProjectSalesOrderRow {
  id: string;
  provisional_ref: string;
  autocount_doc_no?: string | null;
  area_group?: string | null;
  status: SalesOrderStatus;
  grouping_origin: GroupingOrigin;
  line_count: number;
  total_amount: string;
  hard_findings: number;
  warn_findings: number;
  is_pre_order: boolean;
  is_sponsorship: boolean;
  customer_name?: string | null;
  po_number?: string | null;
  created_at?: string | null;
  /** Bumped by any write, including an ingest that adopts a document number. The
   *  divergence lookup keys on it so the amend gate re-evaluates. */
  updated_at?: string | null;

  /**
   * The whole order's one pre-confirmation state (Stage 1B, AC-A03), and how many
   * exceptions stand between it and Needs CS review. Optional because they are derived
   * rather than stored, so a backend that has not shipped the derivation yet simply
   * renders no pill instead of an invented one; explicitly NULL on an order that is not
   * published or amended, which the backend sends rather than omitting.
   */
  review_state?: ReviewState | null;
  exception_count?: number | null;

  /**
   * Not promised by the contract. When present it saves resolving the PO by its number;
   * when absent the panel matches `po_number` against the project's POs instead.
   */
  purchase_order_id?: string | null;
  published_at?: string | null;
  import_file_url?: string | null;
  /**
   * Whether that url may actually be fetched, which is not the same question: a published
   * order carrying an unacknowledged hard finding keeps the address of its file and loses
   * permission to take it. Optional so a cached row from before the field shipped falls
   * back to the url's presence rather than hiding the button.
   */
  can_export?: boolean;
}

export interface ProjectSalesOrderLine {
  id: string;
  line_no: number;
  product_id?: string | null;
  product_code?: string | null;
  description?: string | null;
  qty: string;
  uom?: string | null;
  unit_price: string;
  amount: string;
  delivery_date?: string | null;
  phase_id?: string | null;
  phase_label?: string | null;
  explosion_source: ExplosionSource;
  source_po_line_no?: number | null;
  stock_location?: string | null;
}

export interface ProjectSalesOrderFinding {
  id: string;
  severity: FindingSeverity;
  code: string;
  /** The sentence the backend wrote. Shown as-is; the code is never the message. */
  detail: string;
  line_id?: string | null;
  line_no?: number | null;
  acknowledged_by_name?: string | null;
  acknowledged_reason?: string | null;
  acknowledged_at?: string | null;
}

/** `GET /sales-orders/{pso_id}`: the list row plus lines and findings. */
export interface ProjectSalesOrderDetail extends ProjectSalesOrderRow {
  lines: ProjectSalesOrderLine[];
  findings: ProjectSalesOrderFinding[];
}

// ------------------------------------------------------------- AutoCount worksheet

/**
 * The six header refs AutoCount prints above the lines. `Provisional Ref` is the order's
 * own `provisional_ref` and is not repeated here.
 */
export interface SalesOrderWorksheetHeader {
  debtor?: string | null;
  your_ref_no?: string | null;
  our_ref_no?: string | null;
  our_qt_ref_no?: string | null;
  terms?: string | null;
}

/**
 * One worksheet row, in AutoCount's own column order. Quantities and money stay decimal
 * strings for the same reason the draft lines do. `reserve_qty` is 0 on every row until a
 * confirmed supply decision names a source.
 */
export interface SalesOrderWorksheetLine {
  line_no: number;
  item_code?: string | null;
  description?: string | null;
  reserve_qty: string;
  qty: string;
  delivery_date?: string | null;
  uom?: string | null;
  unit_price: string;
  discount?: string | null;
  total: string;
}

/** `GET /sales-orders/{pso_id}/worksheet`. */
export interface SalesOrderWorksheet {
  id: string;
  provisional_ref: string;
  autocount_doc_no?: string | null;
  status: SalesOrderStatus;
  area_group?: string | null;
  po_number?: string | null;
  customer_name?: string | null;
  header: SalesOrderWorksheetHeader;
  lines: SalesOrderWorksheetLine[];
  total_amount: string;
  findings: ProjectSalesOrderFinding[];
  /** The server's own answer on whether this worksheet may leave the building. */
  can_export: boolean;
  import_file_url?: string | null;
}

export interface SalesOrderPublishResult {
  status: string;
  provisional_ref: string;
  import_file_url?: string | null;
  /** The same gate the row and the worksheet carry. Absent on an older backend. */
  can_export?: boolean;
  autocount_doc_no?: string | null;
  /** How many hard findings this publish waved through. 0 on the ordinary path. */
  acknowledged_findings?: number;
}

/**
 * The publish ask. Omitted entirely on the ordinary path.
 *
 * `acknowledge_blocking` is the one-decision form of the per-finding override: it needs the
 * sales-manager grant (403 without it) and a reason (422 without one), and that reason is
 * recorded on every hard finding it clears.
 */
export interface SalesOrderPublishBody {
  acknowledge_blocking?: boolean;
  reason?: string;
}

export interface SalesOrderLineUpdateBody {
  qty?: string;
  unit_price?: string;
  amount?: string;
  delivery_date?: string | null;
  product_id?: string | null;
  area_group?: string | null;
}

export interface SalesOrderRegroupGroup {
  area_group: string;
  line_ids: string[];
}

// ------------------------------------------------- the whole-document save (edit view)

/**
 * One line inside a whole-document save.
 *
 * `id` is what tells a stored line from a new one: a line already stored carries the id the
 * API gave it, a line added in the session arrives without one, and an id that is not on this
 * order is refused rather than treated as new (which would duplicate the row the client meant
 * to move). `line_no` is NOT sent: position in the array is the order.
 *
 * `amount` is absent on purpose, exactly as it is on the per-line body: it is always
 * `qty * unit_price`, and letting a third number be typed would create a line that fails our
 * own arithmetic check.
 */
export interface SalesOrderLineWriteBody {
  id?: string;
  product_id?: string | null;
  description?: string | null;
  qty: string;
  uom?: string | null;
  unit_price: string;
  delivery_date?: string | null;
  stock_location?: string | null;
}

/**
 * The body of `PUT /sales-orders/{pso_id}`: the header, and the FULL desired line set.
 *
 * `lines` absent leaves the lines exactly as they are. When present it is a REPLACE, so a
 * stored line whose id is missing from it is deleted - the caller must always send the whole
 * set it is showing.
 */
export interface SalesOrderDocumentSaveBody {
  area_group?: string | null;
  lines?: SalesOrderLineWriteBody[];
}

/** What `DELETE /sales-orders/{pso_id}` answers: the reference, and what actually went. */
export interface SalesOrderDeleteResult {
  success: boolean;
  provisional_ref: string;
  deleted: Record<string, number>;
}

/** One order a bulk delete would not touch, named by its reference rather than its id. */
export interface SalesOrderDeleteRefusal {
  id: string;
  provisional_ref: string;
  code: string;
  message: string;
}

/**
 * What `POST /sales-orders/bulk-delete` answers.
 *
 * `refused` is always empty here: a batch that WOULD refuse never reaches this body, because
 * the call is all-or-nothing and is answered 409 before anything is deleted. It is on the
 * shape so a client reads one body either way.
 */
export interface SalesOrderBulkDeleteResult {
  success: boolean;
  deleted_count: number;
  deleted: Record<string, number>;
  refused: SalesOrderDeleteRefusal[];
}

/**
 * One line as the edit session holds it, between Edit and Save.
 *
 * Mirrors `StagedQuotationLine`: the stored row is kept beside the draft because the flags
 * only the server can decide (the phase label, the PO line it exploded from, its findings)
 * are read off it, and a line added in the session simply has none.
 */
export interface StagedSalesOrderLine {
  /** The stored line's id, or null for one added in this session. */
  id: string | null;
  /** The row's identity for as long as the session lasts. Minted by the line table. */
  key: string;
  line: ProjectSalesOrderLine | null;
  draft: Record<string, string>;
  /** Staged for removal: struck through on screen, and gone only once Save runs. */
  removed: boolean;
}

// ------------------------------------------------------------------ amendments

/**
 * Purchasing's own vocabulary, not ours. Order matters: it is the order the summary and
 * the legend read in, mildest first.
 */
export const AMENDMENT_VERBS = [
  'ORDER',
  'RESERVE & ORDER',
  'ADVANCE',
  'DELAY',
  'CHANGE SO NO',
  'CANCEL BALANCE',
] as const;

export type AmendmentVerb = (typeof AMENDMENT_VERBS)[number];

export type AmendmentSourceKind = 'schedule_version' | 'po_version';

export interface AmendmentVersionRef {
  kind: AmendmentSourceKind;
  id: string;
  version_no: number;
  label?: string | null;
}

/** Accepted forms an amendment; declined is recorded with a reason and left out of it. */
export type AmendmentRowDecision = 'accepted' | 'declined';

export interface AmendmentDeltaRow {
  so_line_id: string;
  line_no: number;
  product_code?: string | null;
  description?: string | null;
  verb: AmendmentVerb | string;
  field: string;
  from_value?: string | null;
  to_value?: string | null;
  qty?: string | null;
  phase_label_from?: string | null;
  phase_label_to?: string | null;

  /**
   * GUESS (section 9.3): present once this row belongs to a CREATED amendment, addressing it
   * for `PUT .../amendments/{id}/rows`. Absent on a bare preview - nothing to decide on yet,
   * because nothing has been written.
   */
  row_key?: string;
  /** Defaults to accepted server-side; absent (preview) reads the same way. */
  decision?: AmendmentRowDecision;
  declined_reason?: string | null;
}

/** A phase or product that could not be matched between versions. Never hidden. */
export interface AmendmentUnmatched {
  reason: string;
  detail?: string | null;
}

export interface AmendmentPreview {
  from: AmendmentVersionRef;
  to: AmendmentVersionRef;
  verb_summary: Record<string, number>;
  rows: AmendmentDeltaRow[];
  unmatched: AmendmentUnmatched[];
}

export interface AmendmentPreviewBody {
  po_version_id?: string;
  schedule_version_id?: string;
}

export interface AmendmentCreateBody extends AmendmentPreviewBody {
  reason: string;
}

export interface AmendmentCreated {
  amendment_id: string;
  ocn_id: string;
  ocn_number: string;
  verb_summary: Record<string, number>;
}

/**
 * `GET /amendments/{amendment_id}`. The contract names the route but not its body, so this
 * is the preview shape plus the review state the route must carry to be useful.
 */
export interface AmendmentDetail extends AmendmentPreview {
  id: string;
  status?: string | null;
  reason?: string | null;
  ocn_id?: string | null;
  ocn_number?: string | null;
  ocn_status?: string | null;
  ocn_approver_name?: string | null;
  created_by_name?: string | null;
  created_at?: string | null;
  /** GUESS (section 9.3): counted server-side off `rows[].decision`. */
  accepted_count?: number;
  declined_count?: number;
}

/** `PUT /amendments/{id}/rows` body: one entry per row being decided, keyed by `row_key`. */
export interface AmendmentRowDecisionInput {
  decision: AmendmentRowDecision;
  /** Required by the server when declining; ignored when accepting. */
  reason?: string | null;
}

export interface AmendmentRowDecisionsBody {
  decisions: Record<string, AmendmentRowDecisionInput>;
}

/**
 * One line of the AutoCount change list (section 9.4): what a person keys into AutoCount for
 * an accepted row, in the export's own column order.
 */
export interface AutocountChangeListRow {
  so_number: string;
  line_no: number;
  item_code: string | null;
  product_name?: string | null;
  verb: AmendmentVerb | string;
  old_qty?: string | null;
  new_qty?: string | null;
  old_date?: string | null;
  new_date?: string | null;
  new_so_number?: string | null;
}

export interface AutocountChangeListResponse {
  rows: AutocountChangeListRow[];
  declined_count: number;
}

/**
 * Version pickers. The contract defines `GET /purchase-order-versions/{id}` and
 * `GET /delivery-schedule-versions/{id}` but no way to ENUMERATE either, and both the
 * build step and the delta step have to offer a choice. These are the compact rows the
 * pickers need, a strict subset of the contract's single-version bodies.
 */
export interface ScheduleVersionOption {
  id: string;
  delivery_schedule_id?: string | null;
  version_no: number;
  revision_label?: string | null;
  issuer_party_label?: string | null;
  schedule_date?: string | null;
  po_version_no?: number | null;
  extraction_state?: string | null;
  confirmed_at?: string | null;
}

export interface PoVersionOption {
  id: string;
  version_no: number;
  po_number?: string | null;
  po_date?: string | null;
  extraction_state?: string | null;
  confirmed_at?: string | null;
}

export interface ProjectSalesOrderListParams {
  page?: number;
  limit?: number;
  sort?: string;
  dir?: 'asc' | 'desc';
  query?: string;
  status?: string;
  purchase_order_id?: string;
}
