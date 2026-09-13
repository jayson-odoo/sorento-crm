/**
 * ============================================================================
 * SCM - Order Inquiry upload channel, feature service
 * ============================================================================
 * Layering: OrderInquiryUploadDialog -> THIS service -> lib/api-client -> backend.
 *
 * Renamed from `purchaseHistoryService.ts` (ingest-parity-standardisation S4,
 * AC-P4-1): the purchase-history and sales-history channels this file used to
 * also carry were retired - closed history now arrives through the ESB's own
 * document ingest instead of a separate banded-report upload. What survives
 * is the Order Inquiry sheet, which Project Sales owns (ADR 0010) behind the
 * same `/api/v1/scm/order-inquiry/*` URLs this dialog already called.
 *
 * ── BACKEND CONTRACT, migration tool (PLAN-scm-oi-sheet-migration.md, S1) ──
 *
 *  1) POST /api/v1/scm/order-inquiry/preview     -> 200 OrderInquiryPreview
 *  2) POST /api/v1/scm/order-inquiry/apply       -> 202 ImportQueuedResult
 *  3) GET  /api/v1/scm/order-links/open          -> 200 OpenOrderLinks
 *
 *  multipart body, single field named exactly "file". Auth: `scm.reorder.run`.
 *
 *  Preview returns 200 even for a file it could not read, carrying `ok: false`
 *  and `problems` - the screen has to say WHICH part failed, and an error body
 *  would lose it.
 *
 *  Apply QUEUES the write and answers 202 with the job to watch. The sheet no
 *  longer creates sales orders or writes stock locations (AutoCount owns
 *  both); it raises order inquiry rows against the sales order line the sheet
 *  names and pairs each row to the PO or SPO AutoCount's own linkage states,
 *  falling back to the sheet's own remark only for need AutoCount leaves. A
 *  file the reader cannot use FAILS THE JOB with its problems on it; the only
 *  400 left is "no single active company", which is refused before any job
 *  row exists (this feed writes owned tables).
 *
 *  `OrderInquiryPreview` carries exactly the keys the apply result carries
 *  (UAC AC-S1-22): `preview` computes the same match without writing, so a
 *  count shown before Confirm is the count Confirm will produce.
 *
 * Two calls on purpose: nothing is written from a single click.
 * ============================================================================
 */
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type { ImportQueuedResult } from '@/components/upload-activity/importQueue';
import type { UploadTestResult } from '../components/UploadTestVerdict';

/** Why a sheet row's candidate line was refused, in the order the match checks them. */
export type LineNotFoundReason = 'no_line_for_item' | 'location_differs' | 'qty_exceeds_ordered';

/** A sheet row that named a sales order line but none fit. */
export interface LineNotFoundEntry {
  so_number: string;
  item_code: string;
  qty: number;
  reason: LineNotFoundReason;
}

/** A sales order the sheet named that is not project class, so its rows were refused. */
export interface OrderNotPlannable {
  so_number: string;
  code: string;
}

export interface OrderInquiryPreview {
  ok: boolean;
  problems: string[];
  /** Sheet rows read, before matching. */
  rows: number;
  /** Rows raised as an order inquiry row (linked or not). */
  rows_raised: number;
  /** Rows whose matched line already carries a non-cancelled row: skipped, untouched. */
  rows_already_raised: number;
  /** Count of `line_not_found` below - named separately because the list is capped. */
  rows_line_not_found: number;
  /** Named rows with no matching line, capped at 200. */
  line_not_found: LineNotFoundEntry[];
  /** Sales order numbers the sheet names that the CRM does not hold, capped at 200. */
  sales_orders_not_found: string[];
  /** Sales orders refused for not being project class. */
  orders_not_plannable: OrderNotPlannable[];
  /** Raised rows that gained at least one link, whatever the source. */
  links_written: number;
  /** Raised rows whose link covered only part of the row's qty. */
  links_partial: number;
  /** Raised rows whose link came from AutoCount's own stated linkage, not the sheet's remark. */
  links_from_autocount: number;
  /** Cited document numbers that could not be linked at all, capped at 200. */
  documents_not_linkable: string[];
  sheets_read: string[];
  sheets_skipped: string[];
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

/** What this sheet WOULD raise and link. Writes nothing. */
export function previewOrderInquiry(file: File): Promise<OrderInquiryPreview> {
  return post('/api/v1/scm/order-inquiry/preview', file, 'Failed to read the file');
}

/**
 * Test the inquiry sheet: writes nothing, returns `{valid, errors, warnings, summary}`.
 *
 * Same `?validate_only=true` parameter and same shape as `import-tracking` and the GRN
 * import, so a Test means the same thing wherever somebody presses it.
 */
export function testOrderInquiry(file: File): Promise<UploadTestResult> {
  return post(
    '/api/v1/scm/order-inquiry/apply?validate_only=true', file, 'Failed to test the file',
  );
}

/** Queue the sheet: raise order inquiry rows and pair them to PO/SPO documents. */
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
