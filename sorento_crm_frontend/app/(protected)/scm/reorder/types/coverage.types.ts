/**
 * SCM Purchasing and Fulfilment - Coverage Timeline types (UAC Group B).
 *
 * These mirror, field for field, the backend dataclasses in
 * `app/services/scm/coverage_timeline.py` and `app/services/scm/coverage_service.py`
 * (`TimelineEvent`, `TimelineRow`, `Shortfall`, `TimelineResult`, `SourceAvailability`,
 * `SourceAllocation`, `UndatedDemand`, `Coverage`). The wire contract that Phase 2
 * implements is documented at the top of `services/coverageService.ts`.
 *
 * Two deliberate omissions, both hard rules:
 * - No id fields. `product_id` / `pool_id` are NOT serialised, so a UUID cannot
 *     leak into the UI (AC-B2). Everything is addressed by human code.
 * - No stored timeline. The payload carries `computed_at` because it is computed
 *     per request and never persisted (AC-B6).
 */

/** Event kind. `opening` is the synthetic first row carrying the opening on-hand. */
export type CoverageEventKind = 'opening' | 'demand' | 'supply';

/**
 * Supply stage. In-transit has been loaded and can no longer be re-dated or
 * cancelled; on-order still can. Their sum drives the balance, the split is what a
 * person deciding a quantity reads, so the timeline keeps both.
 */
/**
 * Supply rows carry `in_transit` only. `on_order` stays in the union because older frozen
 * payloads still hold it, but nothing produces it any more: a purchase order is an order
 * placed, not stock on the water, so it is reported as `qty_ordered_not_incoming` and
 * never as a timeline event.
 */
export type CoverageSupplyStage = 'on_order' | 'in_transit';

/**
 * Where a demand line's cover comes from. These are the existing
 * `so_line_allocations.source_type` values, reused rather than reinvented:
 * `own` = the line's own customer bin, `brw` = the shared pool at the same site,
 * `other_project` = another holder's bin behind a claim, `order` = must be bought.
 */
export type CoverageSourceType = 'own' | 'brw' | 'other_project' | 'order';

/** One dated movement. `qty` is signed: negative consumes, positive replenishes. */
export interface CoverageEvent {
  /** ISO date (YYYY-MM-DD). Null only on the opening row. */
  at: string | null;
  qty: number;
  kind: CoverageEventKind;
  /** Document number shown on screen: SO number, PO number, shipment number. */
  ref: string;
  /** Human context: customer, project or supplier name. */
  label: string;
  /** Bin or pool code the movement sits in. */
  location: string;
  /** Populated on supply rows only. */
  supply_stage: CoverageSupplyStage | null;
}

/** One event plus the running balance after it. */
export interface CoverageRow {
  event: CoverageEvent;
  balance: number;
}

/** The first point the balance falls below the floor. */
export interface CoverageShortfall {
  at: string | null;
  /** How much is missing at that point, positive. */
  qty: number;
  /** The document that tipped it. */
  ref: string;
  label: string;
}

/**
 * What could cover the pool's demand right now, split by source. Computed live.
 *
 * `own` is the pool's own bin and `other` the bins that draw on it, because this
 * payload is addressed by product plus pool. Per-line resolution, where `own` means
 * one customer's bin, belongs to fulfilment, which has a line to resolve.
 */
export interface CoverageAvailability {
  own: number;
  pool: number;
  other: number;
  pool_location: string;
  other_locations: string[];
}

/**
 * One resolved slice of cover.
 *
 * These resolve the pool's AGGREGATE demand, not a single sales-order line: the
 * endpoint is addressed by product plus pool and has no line to resolve. Per-line
 * resolution (`CoverageService.resolve_line`) is fulfilment's job, where a line id
 * exists. Empty only when there is no demand at all - a fully covered demand still
 * resolves, to `own` and `brw` slices with `buy_qty` zero, which IS the
 * "use the pool, do not buy" answer.
 */
export interface CoverageAllocation {
  source_type: CoverageSourceType;
  qty: number;
  location: string;
  /** True when the holder has to agree first (`other_project`). */
  needs_claim: boolean;
}

/** A commitment with no date anywhere. Reported, never dated today, never dropped. */
export interface CoverageUndatedDemand {
  so_number: string;
  item_code: string;
  qty: number;
  location: string;
}

/**
 * Cover held at another site. Never netted into the balance: moving it is a
 * physical transfer with a cost and a lead time, so it is a proposal a person
 * accepts (AC-B1d).
 */
export interface CoverageTransferProposal {
  /** Stable key for the accept action. Opaque to the UI, never rendered. */
  proposal_ref: string;
  from_pool_code: string;
  /** What that site holds, so the proposal can be judged rather than just taken. */
  available_qty: number;
  /** What the proposal moves. */
  qty: number;
  transfer_cost: number | null;
  lead_time_days: number | null;
  /** ISO date the moved stock would land, given the lead time. */
  arrives_at: string | null;
}

/** The whole Coverage Timeline for one product at one fulfilment pool. */
export interface CoverageTimeline {
  product_code: string;
  product_name: string | null;
  /** The shared pool the netting is done over. A location with no pool is its own. */
  pool_code: string;
  /** Every location drawing on that pool, in code order. */
  locations: string[];
  /** The level the balance must not fall below. 0 for project demand, ROP otherwise. */
  floor: number;
  opening_balance: number;
  rows: CoverageRow[];
  closing_balance: number;
  shortfall: CoverageShortfall | null;
  /** The worst the balance ever gets. A later event can dig deeper than the first. */
  peak_deficit: number;
  availability: CoverageAvailability;
  /** How the shortfall resolves, cheapest source outward. Empty when nothing is short. */
  allocations: CoverageAllocation[];
  /** Sum of the `order` allocations. Zero means existing stock covers it. */
  buy_qty: number;
  /** True when `buy_qty` is zero: Mr Loo's "BRW" answer written by hand today. */
  use_stock: boolean;
  undated_demand: CoverageUndatedDemand[];
  transfer_proposals: CoverageTransferProposal[];
  /** Planning horizon in months, from tenant config. */
  horizon_months: number;
  /** ISO date the horizon ends. */
  horizon_end: string;
  /** Events dropped for falling beyond `horizon_end`. Stated on screen, never silent. */
  excluded_event_count: number;
  /**
   * In-transit quantity that no allocation places at a warehouse, so it counts for NO
   * pool. Nothing on a shipment names a destination; the allocation does. Adding an
   * unplaceable container to every pool instead would overstate cover on each of them
   * and suppress a purchase per pool, invisibly, so it is set aside and stated here.
   */
  unattributed_in_transit_qty: number;
  /**
   * Placed on a purchase order for this pool with nothing shipped against it yet. Shown
   * BESIDE the balance and deliberately absent from it, so a shortfall does not read as
   * "nobody has done anything about this".
   */
  qty_ordered_not_incoming: number;
  /**
   * Committed demand, and placed on-order supply, carrying no warehouse at all. Both
   * columns are nullable, so these rows belonged to no pool and appeared in no total
   * until they were reported here. A commitment that is in none of the figures is worse
   * than one in the wrong figure: nobody discovers it until a delivery date.
   */
  unplaceable_demand_qty: number;
  unplaceable_on_order_qty: number;
  /** Naive Malaysia wall-clock ISO timestamp of this computation. */
  computed_at: string;
}

/** Result of accepting a cross-site transfer proposal. */
export interface CoverageTransferAcceptResult {
  proposal_ref: string;
  accepted: boolean;
  /** Human reference of whatever the acceptance created, for the toast. */
  transfer_ref: string;
}
