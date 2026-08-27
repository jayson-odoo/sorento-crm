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
 * columns". The column SET is Project and Retail, always (`PLAN_CHANNEL_ORDER`). It was
 * derived from the run's own warehouse segments once, and that made the Project column
 * VANISH on a plan with no project demand, which reads as a missing column rather than as
 * the zero it is. R17 (captain, 28 Aug) ends the derivation outright: a demand channel is
 * `sales_orders.demand_class`, never a warehouse's segment.
 *
 * Each channel column is that channel's OPEN demand for the product - `committed_v`'s split
 * (`project_committed` / `retail_committed`), summed across the product's locations. The
 * channel figures sum to the product's SO (`outstanding_sales`) total by construction, the
 * same invariant `committed_v` guarantees per location. The confirmed subset is carried alongside as `projectConfirmedQty`, shown
 * as an info aside on the Project cell rather than as the cell's own figure.
 *
 * This is a PRESENTATION grouping, not a new calculation: the per-warehouse rows stay the
 * stored facts, and grouping only sums or carries the shared display fields across a
 * product's warehouses. A group row's `rec` is a synthetic aggregate (`id: "group:<product>"`)
 * that exists purely so the grid's existing per-rec cell renderers (`numCell`, the
 * product-keyed popovers) work unmodified on it; it is never sent anywhere itself. S16
 * (captain, 21 Aug): the group row IS decided over now - `usePlanLines.decide`/`.clear` fan
 * the SAME decision out to every `__group.members` recommendation id underneath it, the same
 * way `updateMoq` already fans a MOQ edit out, and the cell reads back the unanimous result
 * (`groupDecisionState`, `lib/planDecisions.ts`) or `mixed` when the members disagree. The
 * per-warehouse rows reached by EXPANDING the group (`GroupMembersPanel`, `PlanLinesGrid.tsx`)
 * stay a read and drill panel - the decision is taken on the group row, never on an
 * individually-expanded member.
 *
 * Supplier / price / MOQ are PRODUCT facts, not per-location facts (captain's ruling,
 * 20 Aug): supplier selection is per supplier-product and never varies by warehouse. Verified
 * on the live run a52b6221 - 4,281 products, zero with more than one distinct `supplier_id`
 * or `unit_cost` across their warehouse rows. So a group row CARRIES the value through when
 * every member agrees, and only falls back to "not on file" on a genuine conflict (which the
 * live data shows does not happen today) - it never invents a figure nobody computed, it just
 * stops discarding one everybody already computed identically.
 *
 * A dash on one of these three fields is NOT one fact - it is two, and they read differently
 * to the buyer. "No member of this group carries a supplier/price/MOQ at all" is a data gap
 * (same as an ungrouped row's own "not on file" dash). "Two or more members carry DIFFERENT
 * values" is a genuine conflict the grouping cannot silently resolve. `__group.conflicts`
 * (below) names which of the three actually landed in the second bucket, so a cell renderer
 * can tell them apart instead of reading every null the same way.
 */
import type { PlanLine } from './planLine';
import type { ReorderRecommendation } from '../types/reorder.types';

export type PlanChannel = 'project' | 'retail';

export const PLAN_CHANNEL_LABEL: Record<PlanChannel, string> = {
  project: 'Project',
  retail: 'Retail',
};

/** Fixed rendering order - Project, then Retail. Not the order channels happen to first
 *  appear in the data. There is no third: "nothing should be unclassified" (captain, P4). */
export const PLAN_CHANNEL_ORDER: PlanChannel[] = ['project', 'retail'];

/** The three product facts that can genuinely conflict across a group's members (see the
 *  file header). Price means `unit_cost` - the Suggested price cell does not yet branch on
 *  this (out of scope here), but the fact is computed uniformly with the other two so it is
 *  available the moment it does. */
export type PlanChannelConflictField = 'supplier' | 'price' | 'moq';

/** What one grouped PRODUCT row carries, beyond the `PlanLine` shape every existing cell
 *  renderer already knows how to read. */
export interface PlanChannelGroupMeta {
  /** The per-warehouse lines this row summarizes, in their existing rank order. Genuine
   *  location-level facts (AutoCount level, safety stock's own warehouse split, ...) live
   *  here, not on the group row. Supplier / price / MOQ are carried onto the group row
   *  itself when uniform across members (captain's 20 Aug ruling, see file header); `members`
   *  is still where a caller reads them per warehouse, and where the expand view drills in. */
  members: PlanLine[];
  /** Every member's warehouse label, always the FULL list (used for the Location cell's
   *  title even when the cell itself shows a shortened "N locations"). */
  locationCodes: string[];
  /** The channel columns THIS GRID renders - `PLAN_CHANNEL_ORDER`, the same set on every
   *  row, so a cell renderer never has to derive one. Carried rather than imported so a
   *  cell reads its row's own answer. */
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
  /** Which of supplier/price/MOQ genuinely CONFLICT across this group's members (two or more
   *  distinct non-null values) - the field reads null on the row precisely when it is a
   *  member of this set. A field that is null WITHOUT being in `conflicts` means no member
   *  carries it at all, a data gap rather than a disagreement (see the file header). */
  conflicts: Set<PlanChannelConflictField>;
  /**
   * The product's OWN plan row, when the run wrote one (`productPlanRowOf`).
   *
   * Null on a run that only ever planned per location, where the group row is the sum of
   * its members exactly as it always was. When it is set, the group row IS this line - the
   * expand panel skips it, because it is the row the reader is already looking at.
   */
  productLine: PlanLine | null;
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

/**
 * The shared value across a product's warehouse rows when every non-null value agrees, else
 * null on a genuine conflict. This is the "product fact, not a per-location fact" rule
 * (captain's 20 Aug ruling): supplier/price/MOQ never legitimately vary by warehouse, so a
 * group row carries the value through rather than discarding it - it only reads null when
 * the members actually disagree (or none of them carry the fact at all).
 *
 * `keyOf` lets object values (a supplier choice) be compared by an identity field (its code)
 * rather than by reference, since two members' supplier objects are never `===` even when
 * they describe the same supplier.
 */
function uniformOrNull<T>(
  values: Array<T | null | undefined>,
  keyOf: (v: T) => string | number = (v) => v as unknown as string | number,
): T | null {
  let result: T | null = null;
  let key: string | number | null = null;
  for (const v of values) {
    if (v === null || v === undefined) continue;
    const k = keyOf(v);
    if (key === null) {
      key = k;
      result = v;
    } else if (k !== key) {
      return null;
    }
  }
  return result;
}

/** Result of `uniformAcrossMembers`: the carried-through value (or null), whether the
 *  members genuinely disagreed, and which member the value came from (null when there was
 *  no winner - nobody carried the fact, or two-plus of them conflicted). */
interface UniformAcrossMembers<T> {
  value: T | null;
  conflict: boolean;
  memberIndex: number | null;
}

/**
 * Like `uniformOrNull`, but keyed off the MEMBER LIST directly rather than a pre-extracted
 * array of values, so a caller gets back two things `uniformOrNull` cannot distinguish: (1)
 * whether a null result means a genuine CONFLICT (two-plus members disagree) versus every
 * member simply lacking the fact, and (2) which member's own value won, so a caller can read
 * that SAME member's associated fields (e.g. its alternatives shortlist) instead of
 * defaulting to `members[0]`, which is not necessarily the member that carried the fact at
 * all (S7b).
 *
 * `isAbsent` lets a caller skip a value that is present but is itself a "nothing here"
 * placeholder (rather than null/undefined) - unused today since every field this grouping
 * reads for supplier/price/MOQ is genuinely null when absent, not a placeholder object.
 */
function uniformAcrossMembers<M, T>(
  members: M[],
  valueOf: (m: M) => T | null | undefined,
  keyOf: (v: T) => string | number = (v) => v as unknown as string | number,
  isAbsent: (v: T) => boolean = () => false,
): UniformAcrossMembers<T> {
  let value: T | null = null;
  let key: string | number | null = null;
  let memberIndex: number | null = null;
  let conflict = false;
  members.forEach((m, i) => {
    const v = valueOf(m);
    if (v === null || v === undefined || isAbsent(v)) return;
    const k = keyOf(v);
    if (key === null) {
      key = k;
      value = v;
      memberIndex = i;
    } else if (k !== key) {
      conflict = true;
    }
  });
  if (conflict) return { value: null, conflict: true, memberIndex: null };
  return { value, conflict: false, memberIndex };
}

/** Compact display text for the Location column - joined codes while short, else a count
 *  (5.3: "the Buy view groups ... Location column shows the warehouse codes joined
 *  compactly ... or 'n locations'"). */
export function locationLabel(codes: string[]): string {
  if (codes.length <= 3) return codes.join(', ');
  return `${codes.length} locations`;
}

/** One synthetic `ReorderRecommendation` standing in for a product's summed warehouses.
 *  Fields the grid reads for a group row are either summed (a true per-location quantity,
 *  e.g. `net_position`, `outstanding_sales`) or carried through uniform-or-null (a PRODUCT
 *  fact that happens to be stored per warehouse row, e.g. `supplier`, `unit_cost`, `moq`,
 *  `order_multiple` - captain's 20 Aug ruling, see file header). Every other field is left
 *  at its neutral/null default so the existing cells' OWN null handling (which already
 *  renders "not on file" honestly) applies rather than inventing a value. AutoCount level
 *  stays per-location (never carried) - it is genuinely a warehouse-level stock setting. */
function buildGroupRec(members: PlanLine[]): ReorderRecommendation {
  const first = members[0];
  const supplierResult = uniformAcrossMembers(
    members,
    (m) => m.rec.supplier,
    (s) => s.supplier_code,
  );
  const supplier = supplierResult.value;
  // The WINNING member's own alternatives, not `first`'s - `first` may be a member that
  // carries no supplier at all while a later member is the one whose value actually won
  // (S7b: a group's alternatives shortlist belongs to whoever supplied the figure).
  const supplierMember =
    supplierResult.memberIndex !== null ? members[supplierResult.memberIndex] : null;
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
    supplier,
    alternatives: supplierMember ? supplierMember.rec.alternatives : [],
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
    moq: uniformOrNull(members.map((m) => m.rec.moq)),
    master_moq: uniformOrNull(members.map((m) => m.rec.master_moq ?? null)),
    moq_is_override: members.every((m) => m.rec.moq_is_override),
    order_multiple: uniformOrNull(members.map((m) => m.rec.order_multiple)),
    policy_type: null,
    supplier_selection: null,
    unit_cost: uniformOrNull(members.map((m) => m.rec.unit_cost)),
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
    // Same treatment as `on_hand`: each member already carries its OWN pool-vs-bin split
    // (captain, 20 Aug), so summing it across the group gives the product's total
    // project-held stock without this file re-deciding which locations count.
    project_on_hand: sumOrNull(members.map((m) => m.rec.project_on_hand)),
    incoming_spo: sumOrNull(members.map((m) => m.rec.incoming_spo)),
    outstanding_po: sumOrNull(members.map((m) => m.rec.outstanding_po)),
    outstanding_sales: sumOrNull(members.map((m) => m.rec.outstanding_sales)),
    project_need: sumOrNull(members.map((m) => m.rec.project_need)),
    retail_need: sumOrNull(members.map((m) => m.rec.retail_need)),
    project_committed: sumOrNull(members.map((m) => m.rec.project_committed)),
    retail_committed: sumOrNull(members.map((m) => m.rec.retail_committed)),
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

/**
 * The row the engine sized for the WHOLE product, if it wrote one.
 *
 * The reorder-level basis plans per PRODUCT (`PLAN-scm-reorder-per-product.md`): one level,
 * one net across every location, one row - and that row names no warehouse, exactly as a
 * network-scope buy already does. It is not a member to be summed with the others, it is
 * the answer; the per-location rows beside it are dispositions, statements about a place.
 *
 * Summing it with them double counted the product (its `on_hand` already spans every
 * location) and, when the covered row was filtered out of the default list, left a BRW
 * disposition standing in as SRTWT7408's plan row: Suggested qty "-", On hand 1,296 of
 * 5,495, Project and Retail both 0, and no way to open the ledger.
 *
 * A disposition never qualifies (it always names its bin), and MORE than one warehouse-less
 * row is not a product row but an ambiguity, so both fall back to summing.
 */
export function productPlanRowOf(members: PlanLine[]): PlanLine | null {
  const rows = members.filter(
    (m) => m.warehouse_id === null && m.rec.warehouse_code == null
      && m.rec.type !== 'disposition',
  );
  return rows.length === 1 ? rows[0] : null;
}

/**
 * The group row for a product the run planned as ONE thing: the product's own row, with the
 * per-location rows carried underneath it.
 *
 * Nothing is summed here, on purpose. Every figure the row shows - on hand, net, the
 * channels, the level, the suggested quantity - is the one the engine froze for the whole
 * product, so adding a member's own copy of it would count the same stock twice.
 */
function buildProductGroupedLine(
  productLine: PlanLine,
  members: PlanLine[],
): GroupedPlanLine {
  const others = members.filter((m) => m.id !== productLine.id);
  const locationCodes = others.map((m) => m.warehouse);
  // The product row FIRST: `usePlanLines` reads a group's level suggestion off the first
  // member that carries one, and the level a per-product plan is decided on is the
  // product's (`pid:`), never a bin's.
  const ordered = [productLine, ...others];
  return {
    ...productLine,
    // Grouped mode drops the Location column, so this only ever reaches a title/search:
    // the locations underneath, not the product row's own empty one.
    warehouse: locationCodes.length ? locationLabel(locationCodes) : productLine.warehouse,
    __group: {
      members: ordered,
      locationCodes,
      channels: PLAN_CHANNEL_ORDER,
      // The product row's own split - it already spans every location (AC-R1).
      channelQty: {
        project: productLine.rec.project_committed ?? null,
        retail: productLine.rec.retail_committed ?? null,
      },
      projectConfirmedQty: productLine.rec.project_need ?? null,
      // One row cannot disagree with itself about its supplier, price or MoQ.
      conflicts: new Set<PlanChannelConflictField>(),
      productLine,
    },
  };
}

function buildGroupedLine(members: PlanLine[]): GroupedPlanLine {
  const productLine = productPlanRowOf(members);
  if (productLine) return buildProductGroupedLine(productLine, members);
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
  };
  // Supplier is a PRODUCT fact (captain's 20 Aug ruling, see file header): carry the
  // member's own supplier object through when every location agrees, and only fall back to
  // the empty placeholder on a genuine conflict. Keyed off `rec.supplier` (null when a
  // member has none) rather than the adapted `m.supplier` placeholder object (`code: ''`
  // when absent) - the placeholder is a display convenience, not a fact, and comparing IT
  // for uniformity previously read "one member has S1, the other has no supplier" as a
  // conflict between 'S1' and '' instead of recognising the second member simply had
  // nothing to disagree with (S7a). Price and the alternatives shortlist follow the same
  // read: the alternatives belong to the WINNING member, not `first` (S7b).
  const supplierResult = uniformAcrossMembers(
    members,
    (m) => m.rec.supplier,
    (s) => s.supplier_code,
  );
  const supplierMember =
    supplierResult.memberIndex !== null ? members[supplierResult.memberIndex] : null;
  const priceResult = uniformAcrossMembers(members, (m) => m.rec.unit_cost);
  const moqResult = uniformAcrossMembers(members, (m) => m.rec.moq);
  // The frozen master MoQ, carried through the same "product fact" way as `moq` itself, so
  // the group cell can show "master N" beside the buyer's own edit. Uniform-or-null, not the
  // effective `moq` a conflict already reads: `isOverride` below is deliberately its OWN,
  // stricter check (every member overridden), because editing the group row applies the same
  // override to every member (20 Aug live test) - a genuine mid-group conflict is never
  // "half overridden" by this grid.
  const masterMoq = uniformOrNull(members.map((m) => m.rec.master_moq ?? null));
  const moqIsOverride = !moqResult.conflict && members.every((m) => m.rec.moq_is_override);
  const conflicts = new Set<PlanChannelConflictField>();
  if (supplierResult.conflict) conflicts.add('supplier');
  if (priceResult.conflict) conflicts.add('price');
  if (moqResult.conflict) conflicts.add('moq');
  return {
    id: rec.id,
    rank: rankOrder ?? 0,
    sku: first.sku,
    product_name: first.product_name,
    type: 'buy',
    order_qty,
    original_order_qty: order_qty,
    // Carried when every location's own price agrees, null on a genuine conflict - see the
    // file header (captain's 20 Aug ruling). The Suggested price / Total cost cells still
    // fall back to their own "no price on file" reading whenever it comes back null,
    // exactly as any other uncosted line does.
    unit_cost: priceResult.value,
    currency: uniformOrNull(members.map((m) => m.currency)),
    unit_cost_base: uniformOrNull(members.map((m) => m.unit_cost_base)),
    net,
    days_cover,
    forecast_daily_demand,
    warehouse: locationLabel(locationCodes),
    supplier: supplierMember
      ? supplierMember.supplier
      : { code: '', name: '', unit_cost: null, lead_time_days: 0 },
    order_qty_inputs: {
      safety_stock: sumOrNull(members.map((m) => m.order_qty_inputs.safety_stock)),
      reorder_point: sumOrNull(members.map((m) => m.order_qty_inputs.reorder_point)),
      order_up_to: sumOrNull(members.map((m) => m.order_qty_inputs.order_up_to)),
      rounded_qty: order_qty,
      moq: moqResult.value,
      master_moq: masterMoq,
      moq_is_override: moqIsOverride,
      order_multiple: uniformOrNull(members.map((m) => m.order_qty_inputs.order_multiple)),
    },
    alternatives: supplierMember ? supplierMember.alternatives : [],
    product_id: first.product_id ?? null,
    warehouse_id: null,
    rec,
    status: first.status,
    purchasable,
    rankOrder,
    __group: {
      members,
      locationCodes,
      channels: PLAN_CHANNEL_ORDER,
      channelQty,
      projectConfirmedQty: sumOrNull(members.map((m) => m.rec.project_need)),
      conflicts,
      productLine: null,
    },
  };
}

/**
 * One row per PRODUCT, summing or carrying-through-when-uniform the shared display fields
 * across the product's warehouses.
 * Channel is analysis inside the row (`__group.channelQty`), never row identity (5.3).
 * Preserves the input's own order: a group is placed at the position of its FIRST member,
 * so a plan already rank-sorted stays rank-sorted (5.1 governs the plan-grain policy this
 * only ever runs under; the caller decides whether to call this at all).
 */
export function groupPlanLinesByChannel(lines: PlanLine[]): GroupedPlanLine[] {
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
  return order.map((key) => buildGroupedLine(buckets.get(key) as PlanLine[]));
}
