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
 * ── BACKEND CONTRACT (app/api/v1/scm/purchase_history.py) ──────────────────
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
 *  Apply QUEUES the write and answers 202 with the job to watch. What it did -
 *  the SO<->PO links it resolved, a per-row outcome for every row - lands on
 *  that job, because the worker has not started when the request answers. A
 *  file the reader cannot use FAILS THE JOB with its problems on it; the only
 *  400 left is "no single active company", which is refused before any job
 *  row exists (this feed writes owned tables).
 *
 * Two calls on purpose: nothing is written from a single click.
 * ============================================================================
 */
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type { ImportQueuedResult } from '@/components/upload-activity/importQueue';
import type { UploadTestResult } from '../components/UploadTestVerdict';

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

/** What this sheet WOULD write. Writes nothing. */
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
