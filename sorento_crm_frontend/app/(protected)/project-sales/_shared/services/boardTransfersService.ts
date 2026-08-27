/**
 * ============================================================================
 * The planning board's own stock transfers (PLAN-scm-planning-inline-decisions section 3.D4)
 * ============================================================================
 * Layering: UI (`BoardTransfersPanel`) -> hook (`useBoardTransfers`) -> THIS service ->
 * `lib/api-client` -> backend.
 *
 * A confirmation on the board writes one `proposed` stock transfer per component whose
 * source is not the line's own location. Those movements used to be found on a different
 * screen, so the planner who raised them never saw them; the board lists the OPEN ones for
 * the orders it is planning, above the product matrix, and approves them there.
 *
 * ── THE CALL ─────────────────────────────────────────────────────────────────
 *
 *   GET /api/v1/inventory/stock-transfers
 *       ?so_numbers=SO404352,SO404353
 *       &state=proposed,approved               <- comma-separated
 *       &limit=200
 *
 *   `so_numbers` filters on the transfer's own sales order, resolved through
 *   `so_line_id -> sales_order_lines -> sales_orders.so_number`. It is a document number,
 *   not an id, because the board itself is addressed by document number (`?orders=SO...`)
 *   and a lookup to ids on the way in would be a round trip for nothing. An unknown number
 *   matches nothing rather than 422ing: a board can legitimately name an order that has
 *   never had a transfer.
 *
 *   Response: the existing `StockTransferListEnvelope` -
 *       { data: StockTransfer[], pagination: { total, page, limit }, empty }
 *
 *   Reads are on `inventory.stock_transfers.view`; the two writes below are on
 *   `inventory.stock_transfers.edit` and are the EXISTING endpoints, unchanged:
 *       POST /api/v1/inventory/stock-transfers/{id}/approve
 *       POST /api/v1/inventory/stock-transfers/bulk-approve   { ids }
 * ============================================================================
 */
import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError } from '@/lib/api-client';
import {
  approveStockTransfer,
  bulkApproveStockTransfers,
} from '@/app/(protected)/inventory-management/stock-transfers/services/stockTransferService';
import type {
  BulkApproveResult,
  StockTransfer,
  StockTransferListEnvelope,
} from '@/app/(protected)/inventory-management/stock-transfers/types/stockTransfer.types';

const BASE = '/api/v1/inventory/stock-transfers';

/** The states the board cares about: what has not moved yet. */
const OPEN_STATES = 'proposed,approved';

export async function listBoardTransfers(
  soNumbers: string[],
): Promise<StockTransferListEnvelope> {
  // No orders, no call: an empty `so_numbers` would filter nothing and page the whole book.
  // The SAME envelope the route answers with, `empty` included, so a reader does not have to
  // tell "nothing was asked" from "asked, and there is nothing".
  if (soNumbers.length === 0) {
    return { data: [], pagination: { total: 0, page: 1, limit: 0 }, empty: true };
  }

  const search = buildDataGridParams(
    // One page, deliberately: a board takes at most 50 orders and a confirmation raises one
    // transfer per moved component, so paging a list somebody is about to approve in bulk
    // would hide half of what the button acts on.
    { pageIndex: 0, pageSize: 200, sorting: [], searchQuery: '' },
    { so_numbers: soNumbers.join(','), state: OPEN_STATES },
  );
  const response = await apiFetch(`${BASE}?${search.toString()}`);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load the stock transfers'));
  }
  return response.json();
}

/** The EXISTING per-row approval, re-exported so the panel has one import for its data. */
export async function approveBoardTransfer(transferId: string): Promise<StockTransfer> {
  return approveStockTransfer(transferId);
}

/** The EXISTING bulk approval, same reason. */
export async function approveBoardTransfers(ids: string[]): Promise<BulkApproveResult> {
  return bulkApproveStockTransfers(ids);
}
