/**
 * ============================================================================
 * SCM - purchase history and Order Inquiry upload channels, feature service
 * ============================================================================
 * Layering: HistoryUploadDialog -> THIS service -> lib/api-client -> backend.
 *
 * ── BACKEND CONTRACT (app/api/v1/scm/purchase_history.py) ──────────────────
 *
 *  1) POST /api/v1/scm/purchase-history/preview  -> 200 PurchaseHistoryPreview
 *     POST /api/v1/scm/purchase-history/apply    -> 200 PurchaseHistoryResult
 *  2) POST /api/v1/scm/order-inquiry/preview     -> 200 OrderInquiryPreview
 *     POST /api/v1/scm/order-inquiry/apply       -> 200 OrderInquiryResult
 *  3) GET  /api/v1/scm/order-links/open          -> 200 OpenOrderLinks
 *
 *  multipart body, single field named exactly "file". Auth: `scm.reorder.run`.
 *
 *  Preview returns 200 even for a file it could not read, carrying `ok: false`
 *  and `problems` - the screen has to say WHICH part failed, and an error body
 *  would lose it. Apply refuses the same file with a 400.
 *
 * Two calls on purpose: nothing is written from a single click.
 *
 * ── WHY THESE ARE SEPARATE FROM THE OUTSTANDING CHANNEL ────────────────────
 *
 * Different files, different meaning. The outstanding extract is the OPEN order
 * book and drives supply. The Purchase Order Listing is HISTORY - it has no
 * received or outstanding column at all - so its lines are written closed and
 * fully received and never count as stock on its way in. The Order Inquiry
 * sheet is neither: it carries the stock location and the SO<->PO pairing that
 * neither of the other two files holds.
 * ============================================================================
 */
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type { UploadTestResult } from '../components/UploadTestVerdict';

/** Which of the two feeds a dialog is driving. */
export type HistoryImportKind = 'purchase-history' | 'order-inquiry' | 'sales-history';

/** What the resolver did after an apply - the pairing may have been claimed months ago. */
export interface OrderLinkResolution {
  examined: number;
  resolved: number;
  so_side: number;
  po_side: number;
  still_open: number;
}

export interface PurchaseHistoryPreview {
  ok: boolean;
  /** Why the file could not be read. Empty when `ok`. */
  problems: string[];
  orders: number;
  orders_new: number;
  orders_existing: number;
  lines: number;
  /** Handling / misc lines: real money, no product behind them. */
  charge_lines: number;
  unmatched_items: number;
  /** Named, not only counted - the list is what somebody takes to the catalogue owner. */
  unmatched_item_codes: string[];
  so_claims: number;
  /** ISO dates (YYYY-MM-DD), null when the file carried no dated order. */
  date_from: string | null;
  date_to: string | null;
}

export interface PurchaseHistoryResult extends PurchaseHistoryPreview {
  orders_created: number;
  lines_created: number;
  links: OrderLinkResolution;
}

export interface OrderInquiryPreview {
  ok: boolean;
  problems: string[];
  rows: number;
  sheets_read: string[];
  sheets_skipped: string[];
  lines_matched: number;
  lines_unmatched: number;
  /** Named, so somebody can see WHICH sales orders have not been uploaded yet. */
  sales_orders_not_found: string[];
  with_location: number;
  unknown_locations: string[];
  po_claims: number;
  /** Rows whose remark is the literal `ORDER`: nothing placed yet, not a parse failure. */
  not_ordered: number;
}

export interface OrderInquiryResult extends OrderInquiryPreview {
  locations_written: number;
  claims_written: number;
  links: OrderLinkResolution;
}

/** Pairings still waiting for one side to be uploaded. */
export interface OpenOrderLinks {
  open: number;
  waiting_for_sales_order: number;
  waiting_for_purchase_order: number;
  sales_orders: string[];
  purchase_orders: string[];
}

function fileBody(file: File): FormData {
  const body = new FormData();
  body.append('file', file);
  return body;
}

async function post<T>(path: string, file: File, fallback: string): Promise<T> {
  const res = await apiFetch(path, { method: 'POST', body: fileBody(file) });
  if (!res.ok) throw new Error(await extractApiError(res, fallback));
  return (await res.json()) as T;
}

/** What this order book WOULD write. Writes nothing. */
export function previewPurchaseHistory(file: File): Promise<PurchaseHistoryPreview> {
  return post('/api/v1/scm/purchase-history/preview', file, 'Failed to read the file');
}

/**
 * Test the order book: writes nothing, returns `{valid, errors, warnings, summary}`.
 *
 * Same `?validate_only=true` parameter and same shape as `import-tracking` and the GRN
 * import, so a Test means the same thing wherever somebody presses it.
 */
export function testPurchaseHistory(file: File): Promise<UploadTestResult> {
  return post(
    '/api/v1/scm/purchase-history/apply?validate_only=true', file, 'Failed to test the file',
  );
}

/** Test the inquiry sheet. Writes nothing. */
export function testOrderInquiry(file: File): Promise<UploadTestResult> {
  return post(
    '/api/v1/scm/order-inquiry/apply?validate_only=true', file, 'Failed to test the file',
  );
}

/** Write the order book. Idempotent on the document number, so a re-upload is safe. */
export function applyPurchaseHistory(file: File): Promise<PurchaseHistoryResult> {
  return post('/api/v1/scm/purchase-history/apply', file, 'Failed to apply the upload');
}

/**
 * The sales book, as HISTORY.
 *
 * Absorbed lines are written closed and fully delivered, so they contribute nothing to
 * committed demand: the client's 11,275-document export left `committed_v` and
 * `net_position_v` byte-identical. The counts worth reading before confirming are
 * `outstanding_lines` (above zero means the file still holds real commitments, which belong
 * to the outstanding channel) and the unknown item / debtor counts.
 */
export interface SalesHistoryPreview {
  ok: boolean;
  orders: number;
  lines: number;
  total_rows: number;
  layout_rows: number;
  /** Rendered strings, the same shape every upload dialog shows. */
  problems: string[];
  unmapped_headers: string[];
  missing_columns: string[];
  non_stock_lines: number;
  unknown_items: string[];
  unknown_item_count: number;
  unknown_debtors: string[];
  unknown_debtor_count: number;
  unknown_locations: string[];
  outstanding_lines: number;
  date_from: string | null;
  date_to: string | null;
}

export interface SalesHistoryResult extends SalesHistoryPreview {
  orders_created: number;
  orders_updated: number;
  orders_unchanged: number;
  lines_created: number;
  lines_updated: number;
  lines_unchanged: number;
  /** Documents this upload settled that still had quantity owed. Never silent. */
  orders_with_open_lines_closed: number;
  /**
   * Documents another feed already owns lines on, so two AutoCount exports disagree about
   * them. Left completely untouched and named here, because which export is current is a
   * question about the client's data rather than something an upload should answer by
   * arriving second.
   */
  conflicted_orders: string[];
  conflicted_order_count: number;
}

/** What this sales book WOULD absorb. Writes nothing. */
export function previewSalesHistory(file: File): Promise<SalesHistoryPreview> {
  return post('/api/v1/scm/sales-history/preview', file, 'Failed to read the file');
}

/** Absorb the sales book. Same -> skip, different -> update, new -> create. */
export function applySalesHistory(file: File): Promise<SalesHistoryResult> {
  return post('/api/v1/scm/sales-history/apply', file, 'Failed to apply the upload');
}

/** What this sheet WOULD write. Writes nothing. */
export function previewOrderInquiry(file: File): Promise<OrderInquiryPreview> {
  return post('/api/v1/scm/order-inquiry/preview', file, 'Failed to read the file');
}

/** Write the stock locations and claim the purchase-order links. */
export function applyOrderInquiry(file: File): Promise<OrderInquiryResult> {
  return post('/api/v1/scm/order-inquiry/apply', file, 'Failed to apply the upload');
}

/**
 * Pairings still waiting for one side.
 *
 * "34 sales orders name a purchase order we have not seen" is how somebody finds out the PO
 * book is a month behind, and there is no other way to find it out.
 */
export async function getOpenOrderLinks(): Promise<OpenOrderLinks> {
  const res = await apiFetch('/api/v1/scm/order-links/open');
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to read the open links'));
  return (await res.json()) as OpenOrderLinks;
}
