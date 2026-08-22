/**
 * P9 allocation wire shapes (AC-H1 to AC-H5).
 *
 * Quantities are decimal STRINGS and stay strings all the way to the screen, exactly as
 * the sales order shapes do: nothing here parses a figure except the display helpers.
 *
 * Ranked candidates are recomputed by the backend on every request and are never stored.
 * Nothing in this file is cached beyond a react-query lifetime for the same reason: a
 * stale on-hand from another project is precisely the number that must not be acted on.
 *
 * Every shape here is a RESPONSE. Stage 1C retired the per-line writes these once had
 * request bodies for: supply is composed and confirmed for the whole sales order in one
 * transaction from Fulfilment Planning, and a cross-project Borrow writes its claim row
 * already accepted, so there is no claim state a reader may change.
 */

/**
 * Where a line's stock comes from. `order` carries no location: it has to be bought.
 * `other_location` joined them in Stage 1C - free stock outside the Reserve pool,
 * borrowed with no donor project to ask.
 */
export type AllocationSourceType =
  | 'brw'
  | 'own'
  | 'other_project'
  | 'other_location'
  | 'order';

/** unallocated -> pending_claim | refused | partial | confirmed. */
export type AllocationState =
  | 'unallocated'
  | 'pending_claim'
  | 'refused'
  | 'partial'
  | 'confirmed';

export type AllocationClaimState = 'requested' | 'accepted' | 'refused';

export const ALLOCATION_SOURCE_LABEL: Record<AllocationSourceType, string> = {
  brw: 'Master location',
  own: 'Available stock',
  other_project: 'Held for another project',
  other_location: 'Free stock elsewhere',
  order: 'Order it',
};

export const ALLOCATION_STATE_LABEL: Record<AllocationState, string> = {
  unallocated: 'No source yet',
  pending_claim: 'Waiting on a claim',
  refused: 'Claim refused',
  partial: 'Partly sourced',
  confirmed: 'Sourced',
};

export const ALLOCATION_CLAIM_STATE_LABEL: Record<AllocationClaimState, string> = {
  requested: 'Waiting',
  accepted: 'Released',
  refused: 'Refused',
};

/** The project a pile is held for, and the CS to ask (AC-H2). */
export interface AllocationHolder {
  project_id: string;
  project_code: string;
  project_title?: string | null;
  cs_user_id?: string | null;
  cs_name?: string | null;
  qty: string;
}

export interface AllocationCandidate {
  rank: number;
  source_type: AllocationSourceType;
  warehouse_id?: string | null;
  warehouse_code?: string | null;
  warehouse_name?: string | null;
  on_hand: string;
  reserved: string;
  held_for_this_project: string;
  held_for_other_projects: string;
  committed: string;
  available: string;
  allocatable: string;
  claimable: string;
  requires_claim: boolean;
  is_project_location: boolean;
  holders: AllocationHolder[];
  open_claim_id?: string | null;
  open_claim_state?: AllocationClaimState | null;
}

export interface AllocationPlanLeg {
  warehouse_id: string;
  warehouse_code?: string | null;
  qty: string;
}

export interface AllocationCandidateList {
  line_id: string;
  line_no: number;
  product_code?: string | null;
  description?: string | null;
  qty: string;
  uom?: string | null;
  delivery_date?: string | null;
  project_code: string;
  brw_warehouse_code?: string | null;
  candidates: AllocationCandidate[];
  plan: AllocationPlanLeg[];
  shortfall: string;
  covered: boolean;
}

export interface AllocationSourceRow {
  id: string;
  source_type: AllocationSourceType;
  warehouse_id?: string | null;
  warehouse_code?: string | null;
  warehouse_name?: string | null;
  source_project_id?: string | null;
  source_project_code?: string | null;
  source_project_cs_name?: string | null;
  qty: string;
  confirmed: boolean;
  confirmed_by_name?: string | null;
  confirmed_at?: string | null;
  claim_id?: string | null;
  claim_state?: AllocationClaimState | null;
  claim_reason?: string | null;
}

export interface AllocationLineRow {
  line_id: string;
  line_no: number;
  product_id?: string | null;
  product_code?: string | null;
  description?: string | null;
  qty: string;
  uom?: string | null;
  delivery_date?: string | null;
  state: AllocationState;
  stock_location?: string | null;
  allocated_qty: string;
  outstanding_qty: string;
  sources: AllocationSourceRow[];
}

export interface AllocationClaimRow {
  id: string;
  state: AllocationClaimState;
  qty: string;
  reason?: string | null;
  from_project_id: string;
  from_project_code: string;
  from_project_title?: string | null;
  from_project_cs_name?: string | null;
  to_project_id: string;
  to_project_code: string;
  to_project_title?: string | null;
  to_project_cs_name?: string | null;
  product_id?: string | null;
  product_code?: string | null;
  product_name?: string | null;
  warehouse_id?: string | null;
  warehouse_code?: string | null;
  so_line_id?: string | null;
  sales_order_id?: string | null;
  sales_order_ref?: string | null;
  line_no?: number | null;
  delivery_date?: string | null;
  requested_by_name?: string | null;
  decided_by_name?: string | null;
  decided_at?: string | null;
  created_at?: string | null;
}

export type AllocationClaimDirection = 'incoming' | 'outgoing' | 'all';

export interface AllocationClaimListParams {
  direction?: AllocationClaimDirection;
  state?: AllocationClaimState[];
  page?: number;
  limit?: number;
}
