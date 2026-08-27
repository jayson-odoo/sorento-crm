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
 * ── CONTRACT (the one thing Phase 2 has to build) ────────────────────────────
 *
 *   GET /api/v1/inventory/stock-transfers
 *       ?so_numbers=SO404352,SO404353          <- NEW in this lane
 *       &state=proposed,approved               <- comma-separated, widened from one value
 *       &limit=200
 *
 *   `so_numbers` filters on the transfer's own sales order, resolved through
 *   `so_line_id -> sales_order_lines -> sales_orders.so_number`. It is a document number,
 *   not an id, because the board itself is addressed by document number (`?orders=SO...`)
 *   and a lookup to ids on the way in would be a round trip for nothing. An unknown number
 *   matches nothing rather than 422ing: a board can legitimately name an order that has
 *   never had a transfer.
 *
 *   Response: the existing `StockTransferListEnvelope` unchanged -
 *       { data: StockTransfer[], pagination: { total, page, limit }, empty }
 *
 *   Reads stay on `inventory.stock_transfers.view`; the two writes below stay on
 *   `inventory.stock_transfers.edit` and are the EXISTING endpoints, unchanged:
 *       POST /api/v1/inventory/stock-transfers/{id}/approve
 *       POST /api/v1/inventory/stock-transfers/bulk-approve   { ids }
 *
 * ── PHASE 1 ─────────────────────────────────────────────────────────────────
 * `USE_MOCK` below is the ONE seam. While it is true the list is served from the fixture in
 * this file and Approve flips it in memory, so every state of the panel (loading, empty,
 * populated, approved, refused) can be tuned with no backend. Phase 2 sets it to false and
 * deletes the fixture; nothing above this file changes. It is DEBT until then, and the
 * Definition of Done gate treats a slice still serving it as unfinished.
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

/** Phase 1 only. See the header: flipping this to false is the whole of the Phase 2 swap. */
const USE_MOCK = true;

const BASE = '/api/v1/inventory/stock-transfers';

/** The states the board cares about: what has not moved yet. */
const OPEN_STATES = 'proposed,approved';

export async function listBoardTransfers(
  soNumbers: string[],
): Promise<StockTransferListEnvelope> {
  if (soNumbers.length === 0) return { data: [], pagination: { total: 0, page: 1, limit: 0 } };
  if (USE_MOCK) return mockList(soNumbers);

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

/** The EXISTING per-row approval. Mocked only so the panel can be tuned without a server. */
export async function approveBoardTransfer(transferId: string): Promise<StockTransfer> {
  if (USE_MOCK) return mockApprove([transferId])[0];
  return approveStockTransfer(transferId);
}

/** The EXISTING bulk approval, same reason. */
export async function approveBoardTransfers(ids: string[]): Promise<BulkApproveResult> {
  if (USE_MOCK) {
    const approved = mockApprove(ids);
    return { approved: approved.length, skipped: [] };
  }
  return bulkApproveStockTransfers(ids);
}

// ---------------------------------------------------------------------------
// PHASE 1 FIXTURE. Deleted with `USE_MOCK`.
//
// The shape is the real `StockTransfer`, so the panel is written against the wire type it
// will actually receive. The numbers are the UAC's own walk: SO404352 line 22, 15 of
// SRTWB7518 moving from the BRW pool to BRW-AM.
// ---------------------------------------------------------------------------

const MOCK_TRANSFERS: StockTransfer[] = [
  {
    id: 'mock-transfer-1',
    transfer_no: 'ST-2026/08-0001',
    state: 'proposed',
    kind: 'pool',
    qty: '15',
    product_id: 'mock-product-1',
    item_code: 'SRTWB7518',
    product_name: 'Wall basin 750mm',
    from_warehouse_id: 'mock-wh-brw',
    from_location: 'BRW',
    to_warehouse_id: 'mock-wh-brw-am',
    to_location: 'BRW-AM',
    sales_order_id: 'mock-so-404352',
    so_number: 'SO404352',
    so_line_no: 22,
    project_sales_order_id: null,
    customer_name: 'Sunway Property',
    sales_agent_id: null,
    agent_code: 'AM',
    agent_name: null,
    supply_decision_id: null,
    revision_no: 1,
    proposed_at: '2026-08-27T02:10:00',
    approved_by: null,
    approved_by_name: null,
    approved_at: null,
    moved_by: null,
    moved_by_name: null,
    moved_at: null,
    cancelled_by: null,
    cancelled_by_name: null,
    cancelled_at: null,
    cancelled_reason: null,
    autocount_ref: null,
    created_at: '2026-08-27T02:10:00',
    updated_at: '2026-08-27T02:10:00',
  },
];

/** Approvals within one browser session, so Approve visibly moves a row (D7). */
const mockState = new Map<string, StockTransfer>();

function mockRow(row: StockTransfer): StockTransfer {
  return mockState.get(row.id) ?? row;
}

function mockList(soNumbers: string[]): StockTransferListEnvelope {
  const wanted = new Set(soNumbers);
  const data = MOCK_TRANSFERS.filter((row) => row.so_number && wanted.has(row.so_number)).map(
    mockRow,
  );
  return { data, pagination: { total: data.length, page: 1, limit: 200 }, empty: data.length === 0 };
}

function mockApprove(ids: string[]): StockTransfer[] {
  const out: StockTransfer[] = [];
  for (const id of ids) {
    const row = mockRow(MOCK_TRANSFERS.find((entry) => entry.id === id) as StockTransfer);
    if (!row || row.state !== 'proposed') continue;
    const approved: StockTransfer = {
      ...row,
      state: 'approved',
      approved_at: new Date().toISOString().slice(0, 19),
      approved_by_name: 'You',
    };
    mockState.set(id, approved);
    out.push(approved);
  }
  return out;
}
