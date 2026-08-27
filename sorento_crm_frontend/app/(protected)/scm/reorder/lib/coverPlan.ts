/**
 * Buy it, cover it from stock we already hold, or both.
 *
 * > "the use stock is use from BRW, not from BRW-IB ... you need to suggest me also, whether
 * >  to buy or use stock, if half half also need to suggest, and also need to suggest use
 * >  stock from where"
 *
 * Mirrors `app/services/scm/cover_service.py`. Two rules it enforces:
 *
 * - A line's OWN on-hand is never a source: it is already inside the net position, so
 *   offering it back would count the same units twice. Cover means stock at ANOTHER
 *   location.
 * - Only a SITE POOL is a source (R18, captain 28 Aug). Stock in a project bin is already
 *   claimed by an Order Inquiry, so a row covered from one would move units that cannot
 *   move - the live tell was "Stock 34" proposed off BRW-IB while BRW held none.
 *
 * ## Why the allocation runs here and not on the server
 *
 * The free pool is shared. Two lines for the same product draw on the same units, so as soon
 * as one line is decided the other's options shrink. The server hands over the pool once,
 * whole; this module spends it down as decisions accumulate, which is the only place that
 * knows what has been decided so far.
 */

/**
 * Where "use stock" may draw from before buying.
 *
 * > "why am I allowed to use stock from other locations? It is either I use stock from BRW,
 * >  or buy."
 *
 * `own_pool` (the default, and what an absent value resolves to) keeps a row's cover inside
 * its own site: only warehouses sharing the row's pool are offered. `all_locations` is the
 * behaviour that shipped first, kept because a single-site company loses nothing by it, and
 * it now has to be asked for explicitly. The knob is the global reorder policy's
 * `cover_scope`, read off the run and applied here so the FE never renders a source the
 * policy has ruled out.
 */
export type CoverScope = 'own_pool' | 'all_locations';

export interface CoverSource {
  warehouse_id: string;
  warehouse_code: string;
  segment: string | null;
  qty: number;
  /**
   * The pool this location belongs to - `COALESCE(pool_warehouse_id, id)`, so a location
   * with no pool of its own IS its own pool. Absent on older payloads, which then scope to
   * the warehouse itself.
   */
  pool_warehouse_id?: string | null;
}

/** How a row's own pool is scoped: the run's setting plus the row's pool. */
export interface CoverScopeOptions {
  /**
   * The run's policy value. Absent reads as `own_pool`, the policy's own default: "we do not
   * know what we are allowed to draw on" has to narrow the offer, not open it up.
   */
  scope?: CoverScope;
  /** `COALESCE(pool_warehouse_id, id)` of the ROW's warehouse. */
  poolWarehouseId?: string | null;
}

/** The pool a source belongs to, falling back to the location itself. */
function poolOf(s: CoverSource): string {
  return s.pool_warehouse_id ?? s.warehouse_id;
}

/**
 * The sources a row may actually draw on.
 *
 * A PROJECT bin is dropped whatever the scope says (R18): it is not an option the policy
 * widens or narrows, it is stock a reorder may never take. The endpoint already excludes
 * it; stating it here too means a cached older payload cannot re-admit one. A location
 * with no segment counts as pool, the same call the engine's own on-hand makes.
 *
 * Under `own_pool` a source has to sit in the row's own pool. A row whose own pool is
 * unknown (a network row carries no warehouse) is NOT filtered to nothing: there is no pool
 * to compare against, so scoping it would silently delete every option rather than narrow
 * them.
 *
 * Only an explicit `all_locations` opens the network. Testing for `scope !== 'own_pool'`
 * failed OPEN: an absent scope (an older payload, a fetch that fell over, a caller that
 * forgot the option) offered every site, which is the one answer the policy default rules
 * out.
 */
export function sourcesInScope(
  free: CoverSource[] | undefined,
  { scope, poolWarehouseId }: CoverScopeOptions = {},
): CoverSource[] {
  const list = (free ?? []).filter((s) => (s.segment ?? 'dealer') !== 'project');
  if (scope === 'all_locations' || !poolWarehouseId) return list;
  return list.filter((s) => poolOf(s) === poolWarehouseId);
}

/** A source with a quantity this row is actually taking (or being offered). */
export type CoverSourceUse = CoverSource;

export interface CoverProposal {
  coverQty: number;
  buyQty: number;
  /**
   * What the proposal DECIDED to take, and from where. Truncated at the shortage: the
   * allocation stops the moment the gap is met, so a location holding plenty appears here
   * with only the units this row needed, and a location the proposal never reached does not
   * appear at all.
   */
  sources: CoverSourceUse[];
  /**
   * What the row may DRAW ON: every in-scope location, at its real free quantity, whether
   * the proposal needed it or not.
   *
   * The two are different questions and conflating them was a real bug: the ledger rendered
   * `sources` as if it were the offer, so a take of 10 out of 50 free was labelled "10 free",
   * a second in-scope location the proposal never reached was invisible, and the input
   * clamped the buyer to the take. Ranked exactly like `sources` (biggest first), and
   * already net of what earlier decisions spent.
   */
  offered: CoverSourceUse[];
  /** Neither whole answer is right: cover what exists and buy the rest. */
  isSplit: boolean;
}

export const NO_COVER: CoverProposal = {
  coverQty: 0,
  buyQty: 0,
  sources: [],
  offered: [],
  isSplit: false,
};

/** What each warehouse has already given away to earlier decisions in this pass. */
export type TakenByWarehouse = Readonly<Record<string, number>>;

export function proposeCover(
  shortage: number,
  lineWarehouseId: string | null,
  free: CoverSource[] | undefined,
  taken: TakenByWarehouse = {},
  scopeOptions: CoverScopeOptions = {},
): CoverProposal {
  if (!(shortage > 0)) return NO_COVER;

  const candidates: CoverSourceUse[] = [];
  for (const s of sourcesInScope(free, scopeOptions)) {
    // Its own stock is already netted. Offering it back is the bug this replaces.
    if (lineWarehouseId && s.warehouse_id === lineWarehouseId) continue;
    const remaining = s.qty - (taken[s.warehouse_id] ?? 0);
    if (remaining <= 0) continue;
    candidates.push({ ...s, qty: remaining });
  }

  // Biggest pile first, the code breaking a tie so two renders cannot disagree. There is
  // no segment ranking any more: after R18 a project bin is not a lower-ranked option, it
  // is not an option at all.
  candidates.sort(
    (a, b) => b.qty - a.qty || a.warehouse_code.localeCompare(b.warehouse_code),
  );

  const used: CoverSourceUse[] = [];
  let covered = 0;
  for (const s of candidates) {
    if (covered >= shortage) break;
    const take = Math.min(s.qty, shortage - covered);
    used.push({ ...s, qty: take });
    covered += take;
  }

  const buyQty = Math.max(0, shortage - covered);
  return {
    coverQty: covered,
    buyQty,
    sources: used,
    offered: candidates,
    isSplit: covered > 0 && buyQty > 0,
  };
}

/** Free stock for a product that no decision has spoken for yet. */
export function remainingFree(
  free: CoverSource[] | undefined,
  taken: TakenByWarehouse,
): number {
  return (free ?? []).reduce(
    (t, s) => t + Math.max(0, s.qty - (taken[s.warehouse_id] ?? 0)),
    0,
  );
}

/**
 * The minimal shape ``coverForLine`` needs off a plan line - kept structural rather than
 * importing `PlanLine` so this stays a leaf module.
 */
export interface CoverableLine {
  order_qty: number;
  warehouse: string;
  warehouse_id: string | null;
  status: string;
  rec: {
    segment?: string | null;
    warehouse_code?: string | null;
    covered_committed?: number | null;
    covered_available?: number | null;
  };
}

/**
 * The ONE place a line's cover proposal is composed, for every rec_type. Both the
 * "Suggested action" cell and the Decision cell read off this, so they can never disagree.
 *
 * A `covered_by_stock` row already carries the engine's own use-stock-or-buy verdict
 * (`covered_committed` / `covered_available` - this SAME pool's own on-hand + on-order, not
 * another warehouse's free pool - see `_covered_rec` in `reorder_run_service.py`). Composing
 * it the same way as an ordinary buy line defaulted it to a full "Buy": `proposeCover`
 * deliberately excludes the line's OWN warehouse (it is already inside the net), so this
 * row's own-pool coverage was invisible to it, and the cross-warehouse free pool usually had
 * nothing spare either - the row read "Buy 15" for a line the engine itself called covered.
 */
export function coverForLine(
  line: CoverableLine,
  free: CoverSource[] | undefined,
  taken: TakenByWarehouse = {},
  scopeOptions: CoverScopeOptions = {},
): CoverProposal {
  if (line.status === 'covered_by_stock') {
    const committed = line.rec.covered_committed ?? line.order_qty;
    const available = Math.max(0, line.rec.covered_available ?? 0);
    if (!(committed > 0)) return NO_COVER;
    const covered = Math.min(committed, available);
    const buyQty = Math.max(0, committed - covered);
    const ownPool = (qty: number): CoverSourceUse => ({
      warehouse_id: line.warehouse_id ?? '',
      warehouse_code: line.rec.warehouse_code ?? line.warehouse,
      segment: line.rec.segment ?? null,
      qty,
    });
    // Offered is what the pool HOLDS available; the take is capped at the commitment. A
    // buyer may draw more of their own pool than the engine proposed, and never more than
    // is there.
    const offered = available > 0 ? [ownPool(available)] : [];
    if (covered <= 0) return { coverQty: 0, buyQty, sources: [], offered, isSplit: false };
    return {
      coverQty: covered,
      buyQty,
      sources: [ownPool(covered)],
      offered,
      isSplit: covered > 0 && buyQty > 0,
    };
  }
  return proposeCover(Math.ceil(line.order_qty), line.warehouse_id, free, taken, scopeOptions);
}

/**
 * What the buyer actually asked for, per source, and what that leaves to buy.
 *
 * > "use stock should behave like the top-up purchase control - a toggle, and when on,
 * >  editable per-location quantities feeding the buy qty."
 *
 * The ONE place a per-location edit turns into a (cover, buy, sources) triple. Both editing
 * surfaces route through it - the ledger's COVER BEFORE BUYING rows and the decision cell's
 * Adjust mixture - so the two can never land on different numbers for the same edit.
 *
 * Each source is clamped to what it was offered (0..qty); a warehouse the proposal never
 * offered is ignored outright rather than invented. The buy is the rest of the SAME shortage
 * the proposal was built for (`coverQty + buyQty`), floored at 0 - a buyer who covers more
 * than the gap is not owed a negative order.
 *
 * The TOTAL is clamped to that same gap as well, not just each source to its own free stock.
 * Without it a buyer who typed 40 into a location holding 50, on a row short of 10, recorded
 * a cover of 40: the buy was floored at 0 so the row itself looked right, but `takenByProduct`
 * then withdrew 40 units from every other row of that product and starved rows that genuinely
 * needed the 30 this one never could use.
 */
export interface CoverEdit {
  coverQty: number;
  buyQty: number;
  sources: CoverSourceUse[];
}

export type SourceEdits = Readonly<Record<string, number>>;

export function applySourceEdits(proposal: CoverProposal, edits: SourceEdits): CoverEdit {
  const gap = coverGap(proposal);
  const sources: CoverSourceUse[] = [];
  let coverQty = 0;
  let budget = gap;
  // OFFERED, not `sources`: the buyer may take from a location the proposal never needed,
  // and up to what that location actually holds. Floored to whole units here rather than at
  // each call site, so no surface can record a fraction of a unit.
  for (const s of proposal.offered) {
    const qty = Math.min(s.qty, wholeUnits(edits[s.warehouse_id]), budget);
    if (qty <= 0) continue;
    sources.push({ ...s, qty });
    coverQty += qty;
    budget -= qty;
  }
  return { coverQty, buyQty: Math.max(0, gap - coverQty), sources };
}

/** The whole shortage a proposal was built for: what it covers plus what it leaves to buy. */
export function coverGap(proposal: CoverProposal): number {
  return proposal.coverQty + proposal.buyQty;
}

/** A typed figure as units: whole, never negative, never NaN. */
function wholeUnits(raw: number | undefined): number {
  return Number.isFinite(raw) ? Math.max(0, Math.floor(raw as number)) : 0;
}

/**
 * The most one location may be set to right now: what it holds free, AND what the row still
 * needs once the OTHER locations are counted.
 *
 * The editing surfaces cap their input with this rather than letting `applySourceEdits` trim
 * the total afterwards, so what the buyer sees in the field is what gets recorded. The cap
 * lands on the field being typed into and never rewrites a figure the buyer set somewhere
 * else: a number moving in a field nobody touched is the more alarming surprise, and freeing
 * a location up by zeroing it first is already the normal way to move units between bins.
 */
export function maxSourceEdit(
  proposal: CoverProposal,
  warehouseId: string,
  edits: SourceEdits,
): number {
  const offered = proposal.offered.find((s) => s.warehouse_id === warehouseId);
  if (!offered) return 0;
  let others = 0;
  for (const s of proposal.offered) {
    if (s.warehouse_id === warehouseId) continue;
    others += Math.min(s.qty, wholeUnits(edits[s.warehouse_id]));
  }
  return Math.max(0, Math.min(offered.qty, coverGap(proposal) - others));
}

/**
 * Turn ONE total ("use 6 from stock") into per-source edits, taken from the front.
 *
 * The proposal already ranked its sources (biggest first), so spending
 * down the front keeps the nearest bins and drops the ones the buyer would have argued about
 * anyway. Lets the Adjust popup, which asks for a single stock figure, go through
 * `applySourceEdits` rather than scaling the split itself.
 */
export function sourceEditsForTotal(proposal: CoverProposal, total: number): SourceEdits {
  let remaining = Math.max(0, total);
  const edits: Record<string, number> = {};
  for (const s of proposal.offered) {
    const take = Math.min(s.qty, remaining);
    edits[s.warehouse_id] = take;
    remaining -= take;
  }
  return edits;
}

/**
 * The default every editing surface starts from: the proposal's own take, and zero for an
 * offered location it did not need. A buyer who touches nothing gets today's answer
 * (AC-3.5), and still sees the other locations they could have used.
 */
export function defaultSourceEdits(proposal: CoverProposal): SourceEdits {
  const edits: Record<string, number> = {};
  for (const s of proposal.offered) edits[s.warehouse_id] = 0;
  for (const s of proposal.sources) edits[s.warehouse_id] = s.qty;
  return edits;
}
