/**
 * Stock transfers - the wire types (`PLAN-scm-cs-planning-uat.md` section E).
 *
 * One shape for the list and the detail: the backend serves the same
 * `StockTransferOut` to both, so a column added there reaches both screens at once.
 */

export type StockTransferState = 'proposed' | 'approved' | 'moved' | 'cancelled';

/** The three words of section 2's vocabulary a movement can carry. */
export type StockTransferKind = 'own_group' | 'pool' | 'borrow';

export interface StockTransfer {
  id: string;
  transfer_no: string;
  state: StockTransferState;
  kind: StockTransferKind;
  qty: string;

  product_id: string | null;
  item_code: string | null;
  product_name: string | null;

  from_warehouse_id: string | null;
  from_location: string | null;
  to_warehouse_id: string | null;
  to_location: string | null;

  sales_order_id: string | null;
  so_number: string | null;
  so_line_no: number | null;
  project_sales_order_id: string | null;
  customer_name: string | null;
  sales_agent_id: string | null;
  agent_code: string | null;
  agent_name: string | null;

  supply_decision_id: string | null;
  revision_no: number | null;

  proposed_at: string | null;
  approved_by: string | null;
  approved_by_name: string | null;
  approved_at: string | null;
  moved_by: string | null;
  moved_by_name: string | null;
  moved_at: string | null;
  cancelled_by: string | null;
  cancelled_by_name: string | null;
  cancelled_at: string | null;
  cancelled_reason: string | null;
  autocount_ref: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface StockTransferListParams {
  query?: string;
  state?: StockTransferState;
  kind?: StockTransferKind;
  from_warehouse_id?: string;
  to_warehouse_id?: string;
  product_id?: string;
  /** The CORE sales order, for the SO detail page's Transfers tab. */
  sales_order_id?: string;
  project_sales_order_id?: string;
  sales_agent_id?: string;
  sort?: string;
  dir?: 'asc' | 'desc';
  page?: number;
  limit?: number;
}

export interface StockTransferListEnvelope {
  data: StockTransfer[];
  pagination: { total: number; page: number; limit: number };
  empty?: boolean;
}

export interface BulkApproveResult {
  approved: number;
  skipped: { id: string; transfer_no: string | null; reason: string }[];
}

/**
 * What each state says on screen.
 *
 * `moved` reads "Moved, awaiting stock upload" AS THE STATE LABEL and nowhere else: our
 * figures follow the next AutoCount upload, and a sentence explaining that under every row
 * would be the on-screen explanation the product does not do.
 */
export const TRANSFER_STATE_LABEL: Record<StockTransferState, string> = {
  proposed: 'Proposed',
  approved: 'Approved',
  moved: 'Moved, awaiting stock upload',
  cancelled: 'Cancelled',
};

/** Section 2's words, so the transfer says where the stock came from the way the board did. */
export const TRANSFER_KIND_LABEL: Record<StockTransferKind, string> = {
  own_group: 'Use own location',
  pool: 'Use shared stock',
  borrow: 'Borrow',
};
