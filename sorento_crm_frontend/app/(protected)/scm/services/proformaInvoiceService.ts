/**
 * ============================================================================
 * SCM proforma invoices - the supplier's priced document, held and read
 * ============================================================================
 * Layering: ProformaInvoicesView / ProformaUploadDialog / ProformaInvoiceDetail
 * -> THIS service -> lib/api-client -> backend.
 *
 * ── BACKEND CONTRACT (app/api/v1/scm/proforma_invoices.py) ─────────────────
 *
 *  POST /api/v1/scm/proforma-invoices/preview  -> 200 ProformaInvoicePreview
 *       multipart: file (required) + supplier_id (required)
 *  POST /api/v1/scm/proforma-invoices/apply    -> 200 ProformaApplyResult
 *       ?validate_only=true                    -> 200 UploadTestResult
 *       multipart: file + supplier_id [+ revision_of] [+ file_as_new]
 *       `revision_of` is JSON `{"<document index>": "<invoice id>"}` - one file holds
 *       several documents, so whether each is a revision is answered per document (AC-E7).
 *       `file_as_new` is JSON `["<document index>"]` - the documents whose offer was
 *       UNTICKED. Needed on top of an absent `revision_of` because the same file derives
 *       the same number: without it the apply lands in place and creates nothing.
 *  GET  /api/v1/scm/proforma-invoices?supplier_id&placement&query&limit&offset -> 200 ProformaInvoiceListResponse
 *       `placement` narrows to not_converted / converted / split (AC-F6). The API defaults
 *       to all of them; the LIST defaults its control to Not converted, which is the
 *       question being asked when somebody opens that screen.
 *       Fixed `created_at DESC` sort, NO page/sort/query params - offset paging only.
 *  GET  /api/v1/scm/proforma-invoices/{id}     -> 200 ProformaInvoiceDetail
 *  DELETE /api/v1/scm/proforma-invoices/{id}   -> 204, hard delete. 409 when this invoice
 *       is already in a packing list.
 *  POST /api/v1/scm/proforma-invoices/bulk-delete -> 200 { deleted, blocked }. Same shape as
 *       the PO book's bulk delete. `blocked` names every invoice skipped because it was
 *       already converted (id, pi_number, shipment_number) - never a silent partial delete.
 *       Auth: `scm.proforma_invoice.upload` (same as single delete).
 *  POST /api/v1/scm/proforma-invoices/convert-to-draft-shipment -> 201
 *       ConvertToDraftShipmentResult. Body: { proforma_invoice_ids: string[],
 *       override_capacity?: boolean, override_reason?: string }. One or more PIs (any
 *       suppliers) become ONE draft inbound shipment, pre-filled with their lines - the
 *       packing-list amendment (PLAN-scm-proforma-to-spo.md). 409 when any given PI was
 *       already converted (names the shipment), or when one is OVER its container's capacity
 *       and no override was given (`detail: 'over_capacity'`, AC-E5). Auth: `scm.reorder.run`
 *       (a shipment write, same permission the packing-list apply path uses).
 *  POST /api/v1/scm/proforma-invoices/{id}/mark-as-revision-of -> 200 ProformaInvoiceDetail
 *       Body: { previous_id }. Links a PI uploaded as new to its predecessor and supersedes
 *       that one (AC-E11). 422 on itself or another supplier's; 409 when either end is
 *       already superseded or already a revision.
 *  PUT  /api/v1/scm/proforma-invoices/{id}          -> 200 ProformaInvoiceDetail
 *       Body: { pi_number?, container_size_id?, lines? }. The whole document as the edit
 *       screen holds it: rows with an `id` update, rows without create, and a line the array
 *       no longer names is deleted. An ABSENT field is left alone; `container_size_id: null`
 *       means the tenant's default size. 409 `duplicate_pi_number` on a rename onto a number
 *       this supplier already uses, and 409 on a superseded revision or an invoice already
 *       converted to a shipment. Auth: `scm.proforma_invoice.upload`.
 *       The per-line `PATCH`/`DELETE` routes still exist on the backend; nothing here calls
 *       them, because a draft that is saved once cannot be sent one line at a time.
 *  GET  /api/v1/scm/proforma-invoices/{id}/export    -> 200 .xlsx bytes, the pre-loading
 *       block layout with the ADJUSTED quantities (AC-E4). Auth: `scm.dashboard.view`.
 *
 * The supplier travels WITH the file because the document never says reliably who wrote
 * it. Currency does NOT travel with it at all (R24): the document states it or the
 * supplier's price list does, and where NEITHER does, the Test verdict names the invoices
 * and Confirm is disabled - a third place to type a currency was one more thing to get
 * wrong on a document that already carries the answer. The backend's `currency` form field
 * is still accepted; nothing in this app sends it.
 * ============================================================================
 */
import { apiFetch } from '@/lib/api';
import { codedError, extractApiError, type CodedError } from '@/lib/api-client';
import {
  filenameFromContentDisposition,
  saveBlobAs,
} from '@/app/(protected)/project-sales/_shared/services/fileDownload';
import type { UploadTestResult } from '../reorder/components/UploadTestVerdict';

/** Where a document's currency came from, in the order AC-P3.1 resolves it. */
export type CurrencySource = 'form' | 'document' | 'supplier_price_list' | 'none';

/** The invoice on file a parsed document looks like a new revision of (AC-E6). A
 *  PROPOSAL: the pre-loading list carries no invoice number, so nothing identifies a resend
 *  except the goods it names, and the operator confirms. */
export interface RevisionCandidate {
  invoice_id: string;
  pi_number: string;
  invoice_date: string | null;
  /** How much of the uploaded document's item codes this invoice already carries. */
  overlap_pct: number;
  matched_items: number;
  lines: number;
}

export interface ProformaDocumentSummary {
  index: number;
  pi_number: string;
  /** False when the number is derived (`PI-<file stem>-<block>`), never stated by the file. */
  pi_number_stated: boolean;
  invoice_date: string | null;
  container_no: string | null;
  bl_no: string | null;
  lines: number;
  qty: number | null;
  total: number | null;
  /** The document's own printed total, when it has one - to compare against `total`. */
  stated_total: number | null;
  unmatched_items: string[];
  currency: string | null;
  currency_source: CurrencySource;
  revision_candidate: RevisionCandidate | null;
}

export interface ProformaInvoicePreview {
  /** Named `ok` to satisfy the shared two-step upload hook. */
  ok: boolean;
  missing_columns: string[];
  problems: string[];
  supplier_id: string;
  supplier_code: string | null;
  supplier_name: string | null;
  documents: ProformaDocumentSummary[];
  document_count: number;
  line_count: number;
  priced_lines: number;
  rows_read: number;
  unmatched_item_codes: string[];
  unmatched_items: number;
  unmapped_headers: string[];
  currency: string | null;
  currency_source: CurrencySource;
  priced_lines_without_currency: number;
}

export interface ProformaApplyResultDocument {
  index: number;
  invoice_id: string;
  pi_number: string;
  invoice_date: string | null;
  currency: string | null;
  currency_source: CurrencySource;
  lines: number;
  revision_no: number;
  revision_of_id: string | null;
  total_amount: number | null;
  unmatched_items: string[];
  created: boolean;
}

export interface ProformaApplyResult {
  documents_created: number;
  documents_updated: number;
  results: ProformaApplyResultDocument[];
  summary: Record<string, unknown>;
}

export interface ProformaInvoiceListRow {
  id: string;
  supplier_id: string;
  supplier_code: string | null;
  supplier_name: string | null;
  pi_number: string;
  invoice_date: string | null;
  currency: string | null;
  container_no: string | null;
  bl_no: string | null;
  total_amount: number | null;
  line_count: number;
  source_ref: string | null;
  block_index: number | null;
  uploaded_by: string | null;
  created_at: string | null;
  updated_at: string | null;
  /** Which box this invoice is measured against - the tenant default when the operator
   *  never chose one. `container_cbm` is that box's loadable volume (40HQ = 65). */
  container_size_id: string | null;
  container_size_code: string | null;
  container_cbm: number | null;
  /** Sum of the lines' total cbm. Null when NO line states a volume (Kailu's shape) -
   *  distinct from 0, which would read as an empty container. */
  total_cbm: number | null;
  /** Lines carrying no volume at all, so a fill figure can say what it is missing. */
  unmeasured_lines: number;
  fill_pct: number | null;
  /** Only when it is over: the cbm above capacity, so the copy never says "over by -3". */
  over_by_cbm: number | null;
  /** `current` or `superseded`. A superseded revision is read-only and never a cost. */
  status: ProformaInvoiceStatus;
  revision_no: number;
  /** How many revisions the chain holds, so a header can read "Revision 2 of 3". */
  revision_count: number;
  adjusted_by: string | null;
  adjusted_at: string | null;
  /** True once any line's qty differs from what the supplier stated, or a line was removed. */
  is_adjusted: boolean;
  /** Where this invoice's goods went, so a converted one is not picked a second time. */
  placement: ProformaPlacement;
  placed_qty: number;
  total_qty: number;
  remaining_qty: number;
  packing_lists: PackingListPlacement[];
}

/** A revision is either the one in force or one the supplier has already replaced. */
export type ProformaInvoiceStatus = 'current' | 'superseded';

/**
 * How much of this invoice has reached a packing list (Q9, AC-F6).
 *
 * `split` is a real state, not a rounding of `converted`: one invoice legitimately sits in
 * two containers, and until every line is placed there is still something to convert.
 */
export type ProformaPlacement = 'not_converted' | 'converted' | 'split';

/** One packing list an invoice (or one of its lines) went to, and how much went there. */
export interface PackingListPlacement {
  shipment_id: string;
  shipment_number: string | null;
  qty: number;
  /** Absent on a per-LINE placement: the container's status is a fact about the container,
   *  and repeating it under every one of its lines is how the two start disagreeing. */
  shipment_status?: string | null;
  /** How many of the invoice's lines landed in this one. Absent on a per-line placement. */
  lines?: number;
}

export interface ProformaInvoiceListResponse {
  data: ProformaInvoiceListRow[];
  total: number;
  limit: number;
  offset: number;
}

export interface ProformaInvoiceLine {
  id: string;
  line_no: number;
  row_number: number | null;
  item_code: string;
  description: string | null;
  qty: number | null;
  uom: string | null;
  unit_price: number | null;
  amount: number | null;
  po_ref: string | null;
  remark: string | null;
  /** How the supplier packs it. Null, never 0, on a document that states no volume - "not
   *  measured" and "takes no room" are different answers to "will this fit" (AC-D1). */
  cartons: number | null;
  cbm_per_unit: number | null;
  cbm_total: number | null;
  /** What the supplier states the line weighs (净重 / 毛重). Null, never 0, on a document
   *  that states neither - same rule as the volumes above. */
  net_weight: number | null;
  gross_weight: number | null;
  /** What the SUPPLIER stated, frozen at import. `qty` / `unit_price` above are ours to
   *  adjust; these two are theirs and are never written again (AC-E2). */
  supplier_qty: number | null;
  supplier_unit_price: number | null;
  /** What we hold, by CODE - the product's, or the SET's when the line names one of our
   *  product sets (R19). Null when the line matched nothing (AC-P1.3). */
  product_code: string | null;
  /** Set only when the line names a product SET, so the cell can badge it rather than read
   *  as a product code the catalogue does not hold. */
  set_code: string | null;
  matched: boolean;
  /** Which rung of the supplier-code ladder bound it, or `manual` for a person's own pick
   *  (R16). Null when the codes agreed exactly - nothing was worked out, so there is
   *  nothing to check. */
  matched_by: string | null;
  match_source: 'auto' | 'manual' | null;
  /** The recorded match, so it can be changed. Null on an exact agreement. */
  match_id: string | null;
  /** Where this line went, once converted to a draft shipment - null until the first
   *  convert. Set only when the line actually became a shipment line. */
  shipment_id: string | null;
  shipment_number: string | null;
  /** Set only when the convert ran and SKIPPED this line (no product match, or no
   *  positive quantity) - distinct from never having been converted at all. */
  unmatched_reason: string | null;
  /** How much of this line has reached a packing list, and what is left to place. */
  placed_qty: number;
  remaining_qty: number;
  packing_lists: PackingListPlacement[];
}

/** Every distinct shipment this invoice's lines went to - normally one, since a convert
 *  refuses re-running on an already-converted invoice. */
export interface ConvertedShipmentRef {
  shipment_id: string;
  shipment_number: string | null;
}

/** One document in the revision chain, oldest first on the detail payload. */
export interface RevisionRef {
  id: string;
  pi_number: string;
  revision_no: number;
  status: ProformaInvoiceStatus;
  invoice_date: string | null;
  total_amount: number | null;
  line_count: number;
}

/** One line the supplier changed between the previous revision and this one (AC-E8).
 *  `occurrence` tells two lines naming the SAME model apart - Kailu's proforma prices one
 *  model on two lines, so the code alone is not a line identity. */
export interface RevisionLineChange {
  item_code: string;
  occurrence: number;
  description: string | null;
  status: 'added' | 'changed' | 'removed';
  qty_was: number | null;
  qty_now: number | null;
  qty_changed: boolean;
  unit_price_was: number | null;
  unit_price_now: number | null;
  unit_price_changed: boolean;
  amount_was: number | null;
  amount_now: number | null;
}

/** What the supplier changed. Null on an original - it has nothing to be compared with. */
export interface RevisionDiff {
  compared_to_id: string;
  compared_to_pi_number: string;
  price_changed_lines: number;
  qty_changed_lines: number;
  added_lines: number;
  removed_lines: number;
  changes: RevisionLineChange[];
}

export interface ProformaInvoiceDetail extends ProformaInvoiceListRow {
  lines: ProformaInvoiceLine[];
  converted_shipments: ConvertedShipmentRef[];
  revisions: RevisionRef[];
  revision_of_pi_number: string | null;
  diff: RevisionDiff | null;
}

/** One PI's outcome inside a convert - always present, so the caller can name every
 *  invoice it asked for, not just the ones with lines. */
export interface ConvertedInvoiceRef {
  id: string;
  pi_number: string;
  supplier_id: string | null;
  supplier_name: string | null;
}

/** A PI line the convert could not carry onto the shipment, and why - reported, never
 *  silently dropped (`inbound_shipment_lines.product_id` is NOT NULL). */
export interface UnmatchedConvertLine {
  proforma_invoice_id: string;
  pi_number: string;
  line_no: number;
  item_code: string;
  reason: string;
}

export interface ConvertToDraftShipmentResult {
  shipment_id: string;
  shipment_number: string | null;
  shipment_status: string;
  supplier_id: string | null;
  lines_created: number;
  lines_skipped: number;
  invoices: ConvertedInvoiceRef[];
  unmatched: UnmatchedConvertLine[];
  /** Invoices in the selection that had nothing left to place - named, never silently
   *  dropped from the count (AC-F7). */
  skipped_invoices: { id: string; pi_number: string; reason: string }[];
}

export interface BulkDeleteProformaResult {
  deleted: number;
  /** Invoices skipped because they were already converted to a draft shipment - named,
   *  never silently dropped from the count. */
  blocked: { id: string; pi_number: string; shipment_number: string | null }[];
}

async function readJson<T>(res: Response, fallback: string): Promise<T> {
  if (!res.ok) throw new Error(await extractApiError(res, fallback));
  return (await res.json()) as T;
}

/** Re-exported: `CodedError` and its reader moved to `lib/api-client`, beside
 *  `extractApiError`, when the supplier-request send needed the same branch (S3, AC-C5).
 *  One owner, one implementation; the callers already importing it from here keep working. */
export type { CodedError };

/** `{ "<document index>": "<invoice id>" }` - which blocks of THIS file revise which
 *  invoice already on file. One file holds several documents, so the answer is per
 *  document, not per upload. */
export type RevisionSelection = Record<string, string>;

function proformaForm(
  file: File,
  supplierId: string,
  revisionOf?: RevisionSelection | null,
  fileAsNew?: string[] | null,
  loadingPlanId?: string | null,
): FormData {
  const body = new FormData();
  body.append('file', file);
  body.append('supplier_id', supplierId);
  if (revisionOf && Object.keys(revisionOf).length > 0) {
    body.append('revision_of', JSON.stringify(revisionOf));
  }
  // An explicit UNTICK. Absent `revision_of` alone cannot say it: a second upload of the
  // same file derives the same document number and would land on the invoice already
  // there, which is what "nothing was created" meant.
  if (fileAsNew && fileAsNew.length > 0) {
    body.append('file_as_new', JSON.stringify(fileAsNew));
  }
  // S6 - the plan that OWNS the invoices this upload writes. Every invoice created or
  // revised here is stamped with it, so the plan reads its own five blocks rather than
  // whichever single invoice sorted first for the supplier.
  if (loadingPlanId) body.append('loading_plan_id', loadingPlanId);
  return body;
}

export async function previewProformaInvoice(
  file: File,
  supplierId: string,
): Promise<ProformaInvoicePreview> {
  const res = await apiFetch('/api/v1/scm/proforma-invoices/preview', {
    method: 'POST',
    body: proformaForm(file, supplierId),
  });
  return readJson<ProformaInvoicePreview>(res, 'Failed to read the proforma invoice');
}

/**
 * Write one proforma invoice per block in the file.
 *
 * ── CONTRACT ADDED BY S6 ───────────────────────────────────────────────────
 * `loadingPlanId` (multipart field `loading_plan_id`, optional) - the plan these invoices
 * belong to. Every invoice this apply creates or revises is stamped with it, so the plan's
 * "They hold" figures are the SUM over its own blocks and a later upload for the same
 * supplier cannot move them. Refused with 422 `invoice_supplier_mismatch` when the plan
 * belongs to a different supplier. Absent (the standalone proforma page) nothing is stamped.
 */
export async function applyProformaInvoice(
  file: File,
  supplierId: string,
  revisionOf?: RevisionSelection | null,
  fileAsNew?: string[] | null,
  loadingPlanId?: string | null,
): Promise<ProformaApplyResult> {
  const res = await apiFetch('/api/v1/scm/proforma-invoices/apply', {
    method: 'POST',
    body: proformaForm(file, supplierId, revisionOf, fileAsNew, loadingPlanId),
  });
  return readJson<ProformaApplyResult>(res, 'Failed to save the proforma invoice');
}

export async function testProformaInvoice(
  file: File,
  supplierId: string,
): Promise<UploadTestResult> {
  const res = await apiFetch('/api/v1/scm/proforma-invoices/apply?validate_only=true', {
    method: 'POST',
    body: proformaForm(file, supplierId),
  });
  return readJson<UploadTestResult>(res, 'Failed to test the proforma invoice');
}

export interface ListProformaInvoicesOptions {
  supplierId?: string | null;
  /** Narrow to what has, or has not, reached a packing list (AC-F6). */
  placement?: ProformaPlacement | null;
  /** The list toolbar's search box: PI number, supplier, container or BL. */
  query?: string | null;
  limit?: number;
  offset?: number;
}

export async function listProformaInvoices(
  opts: ListProformaInvoicesOptions = {},
): Promise<ProformaInvoiceListResponse> {
  const params = new URLSearchParams();
  if (opts.supplierId) params.set('supplier_id', opts.supplierId);
  if (opts.placement) params.set('placement', opts.placement);
  if (opts.query?.trim()) params.set('query', opts.query.trim());
  params.set('limit', String(opts.limit ?? 25));
  params.set('offset', String(opts.offset ?? 0));
  const res = await apiFetch(`/api/v1/scm/proforma-invoices?${params.toString()}`);
  return readJson<ProformaInvoiceListResponse>(res, 'Failed to load proforma invoices');
}

export async function getProformaInvoice(id: string): Promise<ProformaInvoiceDetail> {
  const res = await apiFetch(`/api/v1/scm/proforma-invoices/${id}`);
  return readJson<ProformaInvoiceDetail>(res, 'Failed to load the proforma invoice');
}

/** What a convert may say beyond "these invoices". Every part of it is optional. */
export interface ConvertOptions {
  /** Per PI line, how much to place. Omitted lines place their remaining quantity. */
  lineQuantities?: Record<string, number>;
  /** The operator's answer to an over-capacity refusal, with their reason (AC-E5). */
  override?: { reason: string };
}

/**
 * Several invoices, one NEW draft packing list - any suppliers, one container.
 *
 * `override` carries the operator's "convert anyway" answer to an over-capacity refusal
 * (AC-E5): the reason travels with it, because a container knowingly loaded past its
 * planned volume is a decision somebody made, and the shipment records who and why.
 */
export async function convertProformaInvoicesToDraftShipment(
  invoiceIds: string[],
  options?: ConvertOptions,
): Promise<ConvertToDraftShipmentResult> {
  const override = options?.override;
  const res = await apiFetch('/api/v1/scm/proforma-invoices/convert-to-draft-shipment', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      proforma_invoice_ids: invoiceIds,
      ...(options?.lineQuantities && Object.keys(options.lineQuantities).length > 0
        ? { line_quantities: options.lineQuantities }
        : {}),
      ...(override ? { override_capacity: true, override_reason: override.reason } : {}),
    }),
  });
  if (!res.ok) {
    throw await codedError(res, 'Failed to draft a shipment from the selected invoices');
  }
  return (await res.json()) as ConvertToDraftShipmentResult;
}

/**
 * One line AS THE EDIT SCREEN HOLDS IT.
 *
 * `id` present = update that line; absent = a line the operator added. A line already on the
 * invoice and missing from the array is DELETED - the array is the document.
 */
export interface ProformaInvoiceLineWrite {
  id?: string;
  product_id?: string | null;
  item_code: string;
  description?: string | null;
  qty: number;
  uom?: string | null;
  cartons?: number | null;
  /** Per unit. The total volume is derived server-side, never sent. */
  cbm_per_unit?: number | null;
  unit_price?: number | null;
  net_weight?: number | null;
  gross_weight?: number | null;
}

/** The whole document as one Save. An ABSENT field is left alone - `container_size_id: null`
 *  means the tenant default, which is a different instruction from not mentioning it. */
export interface ProformaInvoiceWrite {
  pi_number?: string;
  container_size_id?: string | null;
  lines?: ProformaInvoiceLineWrite[];
}

/**
 * Link a PI uploaded as new to the document it actually revises (AC-E11).
 *
 * The upload dialog's matching is a proposal, and the pre-loading list carries no invoice
 * number - so a wrong "New PI" is an easy mistake, and an expensive one to be stuck with.
 */
export async function markProformaInvoiceAsRevisionOf(
  invoiceId: string,
  previousId: string,
): Promise<ProformaInvoiceDetail> {
  const res = await apiFetch(
    `/api/v1/scm/proforma-invoices/${invoiceId}/mark-as-revision-of`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ previous_id: previousId }),
    },
  );
  return readJson<ProformaInvoiceDetail>(res, 'Failed to link this revision');
}

/**
 * The whole document, written in ONE call.
 *
 * The detail page edits a LOCAL DRAFT - a struck-through line is not gone until Save - so
 * one PUT carries the number, the container size and the entire line array together. Writing
 * them one at a time is what left a half-applied invoice on screen when the third refused.
 */
export async function saveProformaInvoice(
  invoiceId: string,
  body: ProformaInvoiceWrite,
): Promise<ProformaInvoiceDetail> {
  const res = await apiFetch(`/api/v1/scm/proforma-invoices/${invoiceId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return readJson<ProformaInvoiceDetail>(res, 'Failed to save the proforma invoice');
}

/**
 * The adjusted invoice as a workbook, to send back to the supplier (AC-E4).
 *
 * The name comes from the server's `Content-Disposition` rather than being rebuilt here, so
 * the download and the sheet inside it agree on which invoice this is.
 */
export async function downloadProformaInvoiceExport(
  invoiceId: string,
  fallbackName?: string | null,
): Promise<void> {
  const res = await apiFetch(`/api/v1/scm/proforma-invoices/${invoiceId}/export`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to export the proforma invoice'));
  const filename =
    filenameFromContentDisposition(res.headers.get('Content-Disposition')) ??
    `${fallbackName || 'proforma-invoice'}.xlsx`;
  saveBlobAs(await res.blob(), filename);
}

export async function bulkDeleteProformaInvoices(
  ids: string[],
): Promise<BulkDeleteProformaResult> {
  const res = await apiFetch('/api/v1/scm/proforma-invoices/bulk-delete', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ids }),
  });
  return readJson<BulkDeleteProformaResult>(res, 'Failed to delete the selected invoices');
}
