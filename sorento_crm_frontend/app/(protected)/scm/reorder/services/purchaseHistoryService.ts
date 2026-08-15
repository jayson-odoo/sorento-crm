/**
 * ============================================================================
 * SCM - purchase history and Order Inquiry upload channels, feature service
 * ============================================================================
 * Layering: HistoryUploadDialog -> THIS service -> lib/api-client -> backend.
 *
 * ── BACKEND CONTRACT (app/api/v1/scm/purchase_history.py) ──────────────────
 *
 *  1) POST /api/v1/scm/purchase-history/preview  -> 200 PurchaseHistoryPreview
 *     POST /api/v1/scm/sales-history/preview     -> 200 SalesHistoryPreview
 *     POST /api/v1/scm/order-inquiry/preview     -> 200 OrderInquiryPreview
 *  2) POST /api/v1/scm/{channel}/apply           -> 202 ImportQueuedResult
 *  3) GET  /api/v1/scm/order-links/open          -> 200 OpenOrderLinks
 *
 *  multipart body, single field named exactly "file". Auth: `scm.reorder.run`.
 *
 *  Preview returns 200 even for a file it could not read, carrying `ok: false`
 *  and `problems` - the screen has to say WHICH part failed, and an error body
 *  would lose it.
 *
 *  Apply QUEUES the write and answers 202 with the job to watch. What it did -
 *  counts, the SO<->PO links it resolved, a per-row outcome for every row - lands
 *  on that job, because the worker has not started when the request answers. A
 *  file the reader cannot use FAILS THE JOB with its problems on it; the only 400
 *  left is "no single active company", which is refused before any job row exists
 *  (these feeds write owned tables).
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
import type { ImportQueuedResult } from '@/components/upload-activity/importQueue';
import type { UploadTestResult } from '../components/UploadTestVerdict';

/** Which of the two feeds a dialog is driving. */
export type HistoryImportKind = 'purchase-history' | 'order-inquiry' | 'sales-history';

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

export interface OrderInquiryPreview {
  ok: boolean;
  problems: string[];
  rows: number;
  sheets_read: string[];
  sheets_skipped: string[];
  /**
   * Distinct scheduled deliveries the sheet describes: `(sales order, item, delivery date)`.
   * Lower than `rows`, and that is the point. The book states one instalment on a month tab, a
   * roll-up tab covering that month and a dated working snapshot, so the row count is not the
   * amount of demand.
   */
  instalments: number;
  /** Rows absorbed into an instalment already stated on another sheet. */
  rows_restating_an_instalment: number;
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
 * import, so a Test means the same thing wherever somebody presses it. Still synchronous
 * after the apply went to the queue: it writes nothing and the operator is waiting for it.
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

/** Queue the order book. Idempotent on the document number, so a re-upload is safe. */
export function applyPurchaseHistory(file: File): Promise<ImportQueuedResult> {
  return post('/api/v1/scm/purchase-history/apply', file, 'Failed to queue the upload');
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

/** What this sales book WOULD absorb. Writes nothing. */
export function previewSalesHistory(file: File): Promise<SalesHistoryPreview> {
  return post('/api/v1/scm/sales-history/preview', file, 'Failed to read the file');
}

/** Queue the sales book. Same -> skip, different -> update, new -> create. */
export function applySalesHistory(file: File): Promise<ImportQueuedResult> {
  return post('/api/v1/scm/sales-history/apply', file, 'Failed to queue the upload');
}

/** What this sheet WOULD write. Writes nothing. */
export function previewOrderInquiry(file: File): Promise<OrderInquiryPreview> {
  return post('/api/v1/scm/order-inquiry/preview', file, 'Failed to read the file');
}

/** Queue the sheet: project demand, stock locations, and the purchase-order claims. */
export function applyOrderInquiry(file: File): Promise<ImportQueuedResult> {
  return post('/api/v1/scm/order-inquiry/apply', file, 'Failed to queue the upload');
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
