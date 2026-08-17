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

export type SalesOrderStatus =
  | 'draft'
  | 'blocked'
  | 'ready'
  /** Sponsorship only (AC-K3): drafted at price zero, waiting on Accounts. Gates publish. */
  | 'awaiting_costing'
  | 'published'
  | 'amended';

/** Where the area split came from. The split is a proposal, never a rule (AC-F4a). */
export type GroupingOrigin = 'area' | 'learned' | 'manual' | 'subset';

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
   * Not promised by the contract. When present it saves resolving the PO by its number;
   * when absent the panel matches `po_number` against the project's POs instead.
   */
  purchase_order_id?: string | null;
  published_at?: string | null;
  import_file_url?: string | null;
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
  autocount_doc_no?: string | null;
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
