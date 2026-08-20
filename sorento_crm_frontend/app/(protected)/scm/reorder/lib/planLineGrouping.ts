/**
 * Product-grain grouping for the Buy view (PLAN-scm-front-planning.md 5.3).
 *
 * > "my expectation is 1 line of retail, 1 line of project, simple as that" - a buyer on a
 * >  Product-grain run saw the same SKU three times (one bare-site Retail row, two
 * >  suffixed-bin Project rows) because `PlanLinesGrid` renders one row per stored
 * >  recommendation, and the stored grain is always (product, warehouse) - Location need is
 * >  never re-netted, only re-presented (5.4).
 *
 * SUPERSEDES the first cut of this file (grouped to one row per (product, channel)): the
 * captain's refined ask is ONE row per PRODUCT, with channel as COLUMNS rather than row
 * identity - "instead of 1 column SO, 1 column project, 1 column retail, it should be 2
 * columns". The column SET is dynamic, derived from `channelOf` across the run's own rows
 * (today: Project, Retail, and Unclassified only when a row actually carries it) - never
 * hardcoded to two.
 *
 * Each channel column is that channel's OPEN demand for the product - `committed_v`'s split
 * (`project_committed` / `retail_committed` / `unclassified_committed`), summed across the
 * product's locations - NOT `project_need` (the confirmed-for-buy SUBSET of
 * `project_committed`, 5.3). The three channel figures sum to the product's SO
 * (`outstanding_sales`) total by construction, the same invariant `committed_v` guarantees
 * per location. The confirmed subset is carried alongside as `projectConfirmedQty`, shown
 * as an info aside on the Project cell rather than as the cell's own figure.
 *
 * This is a PRESENTATION grouping, not a new calculation: the per-warehouse rows stay the
 * stored facts, and grouping only sums the shared display fields across a product's
 * warehouses. A group row's `rec` is a synthetic aggregate that exists purely so the grid's
 * existing per-rec cell renderers (`numCell`, the product-keyed popovers) work unmodified on
 * it; it is never sent anywhere and never decided over directly (`decisionsReadOnly` is
 * already true on every Product-grain run - 5.4 - so a group row is read/drill only exactly
 * like the rows it summarizes).
 */
import type { PlanLine } from './planLine';
import type { ReorderRecommendation } from '../types/reorder.types';

export type PlanChannel = 'project' | 'retail' | 'unclassified';

export const PLAN_CHANNEL_LABEL: Record<PlanChannel, string> = {
  project: 'Project',
  retail: 'Retail',
  unclassified: 'Unclassified',
};

/** Fixed rendering order - Project, then Retail, then Unclassified when it is present at
 *  all. Not the order channels happen to first appear in the data. */
export const PLAN_CHANNEL_ORDER: PlanChannel[] = ['project', 'retail', 'unclassified'];

/**
 * Warehouse `segment` -> channel (5.2/5.4: channel is a warehouse fact for THIS mapping,
 * `dealer` for the bare site and `project` for a suffixed bin). A missing segment is never
 * guessed at - it reads Unclassified, the same word the need/committed columns already use
 * for demand with no persisted class, rather than being folded into Retail.
 *
 * Used only to derive WHICH channel columns the grid renders (`presentChannels` below) and
 * to keep the per-warehouse expand rows legible - never to decide a channel COLUMN's
 * quantity, which reads `committed_v`'s own product-location split instead (5.3).
 */
export function channelOf(line: Pick<PlanLine, 'rec'>): PlanChannel {
  const seg = line.rec.segment;
  if (seg === 'project') return 'project';
  if (seg === 'dealer') return 'retail';
  return 'unclassified';
}

/**
 * Which channel columns the grid renders, dynamically, off the rows actually present -
 * never hardcoded to Project + Retail. Computed once over the WHOLE list passed in (not
 * per product), so every product row in a grouped grid shares the same column set rather
 * than a jagged table where one row grows a third column the others lack.
 *
 * Project and Retail are gated on a warehouse actually carrying that segment
 * (`channelOf`'s per-row read). Unclassified is gated differently, on purpose: a warehouse
 * with no persisted segment folds into Unclassified by `channelOf` even when it happens to
 * carry NO open demand there, and rendering the column for that alone is exactly what the
 * captain rejected - "I don't need unclassified, nothing should be unclassified by right"
 * (19 Aug). So Unclassified shows only when the run's `unclassified_committed` actually
 * sums to something nonzero somewhere on the page - a genuine gap to close, not a warehouse
 * that merely lacks a segment tag.
 */
export function presentChannels(lines: Pick<PlanLine, 'rec'>[]): PlanChannel[] {
  const present = new Set(lines.map(channelOf));
  const hasUnclassifiedDemand = lines.some((l) => (l.rec.unclassified_committed ?? 0) !== 0);
  return PLAN_CHANNEL_ORDER.filter((c) =>
    c === 'unclassified' ? hasUnclassifiedDemand : present.has(c),
  );
}

/** What one grouped PRODUCT row carries, beyond the `PlanLine` shape every existing cell
 *  renderer already knows how to read. */
export interface PlanChannelGroupMeta {
  /** The per-warehouse lines this row summarizes, in their existing rank order. Every
   *  location-level fact (price, supplier, MOQ, AutoCount level, ...) lives here, not on
   *  the group row, because those are per-location facts and summing them would invent a
   *  figure nobody computed. */
  members: PlanLine[];
  /** Every member's warehouse label, always the FULL list (used for the Location cell's
   *  title even when the cell itself shows a shortened "N locations"). */
  locationCodes: string[];
  /** The channel columns THIS GRID renders (shared across every product row - see
   *  `presentChannels`), so a cell renderer never has to re-derive the column set itself. */
  channels: PlanChannel[];
  /** This product's OPEN demand per channel - `committed_v`'s split, summed across the
   *  product's locations (5.3). NULL is UNAVAILABLE (a legacy run carries no split), a
   *  different fact from a channel that genuinely needs nothing and must not read as it.
   *  The populated entries sum to `rec.outstanding_sales`. */
  channelQty: Partial<Record<PlanChannel, number | null>>;
  /** The CONFIRMED-for-buy subset of `channelQty.project` (`project_need` summed) - firm
   *  demand that bypasses Retail netting entirely (5.3). Shown as an info aside on the
   *  Project cell ("N confirmed for buy"), never as the cell's own figure, since the cell
   *  states the channel's whole open demand like its siblings do. */
  projectConfirmedQty: number | null;
}

export interface GroupedPlanLine extends PlanLine {
  __group: PlanChannelGroupMeta;
}

export function isGroupedLine(line: PlanLine): line is GroupedPlanLine {
  return Object.prototype.hasOwnProperty.call(line, '__group') && !!(line as GroupedPlanLine).__group;
}

function sumOrNull(values: Array<number | null | undefined>): number | null {
  let sum = 0;
  let any = false;
  for (const v of values) {
    if (v === null || v === undefined) continue;
    sum += v;
    any = true;
  }
  return any ? sum : null;
}

function minOrNull(values: Array<number | null | undefined>): number | null {
  let min: number | null = null;
  for (const v of values) {
    if (v === null || v === undefined) continue;
    if (min === null || v < min) min = v;
  }
  return min;
}

/** Compact display text for the Location column - joined codes while short, else a count
 *  (5.3: "the Buy view groups ... Location column shows the warehouse codes joined
 *  compactly ... or 'n locations'"). */
export function locationLabel(codes: string[]): string {
  if (codes.length <= 3) return codes.join(', ');
  return `${codes.length} locations`;
}

/** One synthetic `ReorderRecommendation` standing in for a product's summed warehouses.
 *  Only the fields the grid actually reads for a group row are aggregated; every other
 *  field is left at its neutral/null default so the existing cells' OWN null handling
 *  (which already renders "not on file" honestly) applies rather than inventing a value -
 *  price, supplier, MOQ and AutoCount level are per-location facts and are never summed. */
function buildGroupRec(members: PlanLine[]): ReorderRecommendation {
  const first = members[0];
  return {
    id: `group:${first.product_id ?? first.sku}`,
    type: 'buy',
    sku: first.sku,
    product_name: first.product_name,
    abc_class: null,
    xyz_class: null,
    warehouse_code: null,
    warehouse_name: null,
    product_id: first.product_id ?? null,
    warehouse_id: null,
    pool_warehouse_id: first.rec.pool_warehouse_id ?? null,
    is_network: false,
    allocation: null,
    order_qty: sumOrNull(members.map((m) => m.order_qty)) ?? 0,
    recommended_qty: sumOrNull(members.map((m) => m.rec.recommended_qty)),
    reorder_point: null,
    min_qty: null,
    max_qty: null,
    order_up_to: null,
    net_position: sumOrNull(members.map((m) => m.net)),
    days_of_cover: null, // recomputed on the PlanLine itself, from summed net/forecast
    reason: null,
    reason_label: null,
    confidence: null,
    sample_size: 0,
    supplier: null,
    alternatives: [],
    is_exception: false,
    disposition_action: null,
    transfer_flag: null,
    forecast_daily_demand: sumOrNull(members.map((m) => m.forecast_daily_demand)),
    lead_time_days: null,
    lead_time_source: null,
    safety_stock: null,
    safety_stock_method: null,
    safety_stock_fallback: null,
    service_level: null,
    safety_days: null,
    review_days: null,
    moq: null,
    order_multiple: null,
    policy_type: null,
    supplier_selection: null,
    unit_cost: null,
    cash_impact: null,
    rank: minOrNull(members.map((m) => m.rankOrder)),
    rank_score: null,
    funding_status: null,
    days_to_stockout: null,
    rank_factors: [],
    // No single warehouse's segment describes a product row spanning several channels -
    // the channel columns (`__group.channelQty`) are the honest read, not this field.
    segment: null,
    on_hand: sumOrNull(members.map((m) => m.rec.on_hand)),
    incoming_spo: sumOrNull(members.map((m) => m.rec.incoming_spo)),
    outstanding_po: sumOrNull(members.map((m) => m.rec.outstanding_po)),
    outstanding_sales: sumOrNull(members.map((m) => m.rec.outstanding_sales)),
    project_need: sumOrNull(members.map((m) => m.rec.project_need)),
    retail_need: sumOrNull(members.map((m) => m.rec.retail_need)),
    unclassified_need: sumOrNull(members.map((m) => m.rec.unclassified_need)),
    project_committed: sumOrNull(members.map((m) => m.rec.project_committed)),
    retail_committed: sumOrNull(members.map((m) => m.rec.retail_committed)),
    unclassified_committed: sumOrNull(members.map((m) => m.rec.unclassified_committed)),
    // The reorder-level columns (19-20 Aug follow-up): `master_reorder_level` /
    // `master_reorder_quantity` are PRODUCT-record facts (`products.reorder_level` /
    // `.reorder_quantity`), joined onto every one of this product's warehouse rows
    // identically - carrying the first member's copy through loses nothing, unlike summing
    // a per-location figure. Left OUT of `buildGroupRec` before this fix, a group row's
    // "Reorder level" / "Reorder qty" cells read `undefined` and fell through to the
    // column's own "not set" dash even for a product the master DOES carry a level for
    // (captain: SRTWCX8861-S, `products.reorder_level=10`). The buyer's OWN level
    // (`reorder_level`, `scm.reorder_level`) stays out: unlike the master figure it can
    // genuinely differ per warehouse, and inventing one group-wide value for it would be
    // exactly the kind of summed-per-location guess this function otherwise refuses to make.
    master_reorder_level: first.rec.master_reorder_level ?? null,
    master_reorder_quantity: first.rec.master_reorder_quantity ?? null,
  } as ReorderRecommendation;
}

function buildGroupedLine(members: PlanLine[], channels: PlanChannel[]): GroupedPlanLine {
  const first = members[0];
  const locationCodes = members.map((m) => m.warehouse);
  const rankOrder = minOrNull(members.map((m) => m.rankOrder));
  const order_qty = sumOrNull(members.map((m) => m.order_qty)) ?? 0;
  const net = sumOrNull(members.map((m) => m.net));
  const forecast_daily_demand = sumOrNull(members.map((m) => m.forecast_daily_demand));
  // Recomputed from the summed net/forecast rather than averaged per-location ratios, so
  // the runway a group shows is the same arithmetic a single combined location would give.
  const days_cover =
    net !== null && forecast_daily_demand !== null && forecast_daily_demand > 0
      ? net / forecast_daily_demand
      : null;
  const purchasable = members.some((m) => m.purchasable);
  const rec = buildGroupRec(members);
  const channelQty: Partial<Record<PlanChannel, number | null>> = {
    project: sumOrNull(members.map((m) => m.rec.project_committed)),
    retail: sumOrNull(members.map((m) => m.rec.retail_committed)),
    unclassified: sumOrNull(members.map((m) => m.rec.unclassified_committed)),
  };
  return {
    id: rec.id,
    rank: rankOrder ?? 0,
    sku: first.sku,
    product_name: first.product_name,
    type: 'buy',
    order_qty,
    original_order_qty: order_qty,
    // Never summed - a per-unit price averaged across locations would misstate what any
    // one PO actually costs. The Suggested price / Total cost cells fall back to their own
    // "no price on file" reading, same as any other uncosted line.
    unit_cost: null,
    currency: null,
    unit_cost_base: null,
    net,
    days_cover,
    forecast_daily_demand,
    warehouse: locationLabel(locationCodes),
    supplier: { code: '', name: '', unit_cost: null, lead_time_days: 0 },
    order_qty_inputs: {
      safety_stock: sumOrNull(members.map((m) => m.order_qty_inputs.safety_stock)),
      reorder_point: sumOrNull(members.map((m) => m.order_qty_inputs.reorder_point)),
      order_up_to: sumOrNull(members.map((m) => m.order_qty_inputs.order_up_to)),
      rounded_qty: order_qty,
      moq: null,
      order_multiple: null,
    },
    alternatives: [],
    product_id: first.product_id ?? null,
    warehouse_id: null,
    rec,
    status: first.status,
    purchasable,
    rankOrder,
    __group: {
      members,
      locationCodes,
      channels,
      channelQty,
      projectConfirmedQty: sumOrNull(members.map((m) => m.rec.project_need)),
    },
  };
}

/**
 * One row per PRODUCT, summing the shared display fields across the product's warehouses.
 * Channel is analysis inside the row (`__group.channelQty`), never row identity (5.3).
 * Preserves the input's own order: a group is placed at the position of its FIRST member,
 * so a plan already rank-sorted stays rank-sorted (5.1 governs the plan-grain policy this
 * only ever runs under; the caller decides whether to call this at all).
 */
export function groupPlanLinesByChannel(lines: PlanLine[]): GroupedPlanLine[] {
  const channels = presentChannels(lines);
  const order: string[] = [];
  const buckets = new Map<string, PlanLine[]>();
  for (const line of lines) {
    const key = line.product_id ?? `sku:${line.sku}`;
    const bucket = buckets.get(key);
    if (bucket) {
      bucket.push(line);
    } else {
      buckets.set(key, [line]);
      order.push(key);
    }
  }
  return order.map((key) => buildGroupedLine(buckets.get(key) as PlanLine[], channels));
}
