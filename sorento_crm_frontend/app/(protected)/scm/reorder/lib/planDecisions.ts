/**
 * What the buyer decided, and what it adds up to.
 *
 * > "you don't tell me what's over or within budget, because I haven't decided which one i
 * >  want to buy, which one i want to use existing stock ... during planning, I don't even
 * >  need to specify the budget, I should check my budget at the end of decisions made for all
 * >  products"
 *
 * The old screen ran this backwards: a budget was assumed, the allocator spent it, and the
 * buyer reacted to a split they had not authorised. Here nothing is spent until a decision is
 * taken, and the budget is a question asked of the finished decisions.
 *
 * ## Undecided is a state, not a default
 *
 * The single most important rule in this file. The old screen treated a within-budget line as
 * implicitly fundable, so a plan the buyer had not finished reading looked like a plan they
 * had agreed to. A line nobody has touched is `undecided`: it is not a buy, it is not a skip,
 * it is counted and reported separately, and it never enters a total. "I have not got to it
 * yet" must never render as "there is nothing left to buy".
 */
import { m8CashImpact } from './planRow';
import type { PlanLine } from './planLine';
import type {
  PlanRowDecision as ServerPlanDecision,
  PlanRowDecisionKind,
  PlanRowDecisionListResponse,
  PlanRowPriceMode,
  RecordPlanRowDecisionPayload,
} from '../types/decisions.types';

export type PlanDecisionKind = 'buy' | 'use_stock' | 'use_po' | 'skip';

/**
 * One decision is a MIXTURE, not a choice (S16, user: "we should allow mixture of
 * actions"). A 200-unit shortage can be met by 50 from another bin, 100 already on a PO,
 * and an order for the last 50 - that is ONE decision with three parts, and forcing the
 * buyer to pick a single kind is what made "Use PO" look like it forbade buying.
 *
 * Zero/absent parts are omitted. `skip` is the exception: deliberately doing nothing is
 * exclusive of every part, and still distinct from undecided (the absence of the entry).
 */
export interface PlanDecision {
  /** Units to order. */
  buy?: number;
  /**
   * Units taken from other bins, with their sources. "Use stock" without a source is not
   * a decision anybody can act on, and it is what makes the pool spendable - two lines
   * drawing on the same units have to be able to see what the other took.
   */
  stock?: { qty: number; sources: { warehouse_id: string; warehouse_code: string; qty: number }[] };
  /** Units left to the existing PO book - already ordered, nothing to do. */
  po?: number;
  /** Deliberately do nothing this round. Exclusive with the parts above. */
  skip?: boolean;
  /** Why the buyer departed from the suggestion, carried onto the adjustment. */
  reason?: string;
  /**
   * How the buy is priced (AC-R13). `use_last` costs it at what we last paid the chosen
   * supplier; `ask_new` says the price is still a question, so the drafted PO line goes
   * out unpriced rather than carrying a figure nobody quoted. Absent = `use_last`.
   */
  priceMode?: PlanRowPriceMode;
  /**
   * The supplier the buyer chose (AC-R14), as its CODE. Absent = the engine's own
   * proposal stands. Switching it re-reads that supplier's last price and lead time.
   */
  supplierCode?: string;
  /**
   * The decision has already been confirmed into a draft purchase order - the server
   * stamped `draft_po_number` on it. Read-only here: nothing on the FE sets it, and the
   * status pill needs it to say "Confirmed" rather than "Saved" (plan 4.3).
   */
  confirmed?: boolean;
}

/** The default price call, so "not stated" and "use the last price" never diverge. */
export const DEFAULT_PRICE_MODE: PlanRowPriceMode = 'use_last';

export type PlanDecisionMap = Readonly<Record<string, PlanDecision | undefined>>;

/**
 * Units this line will actually order. Anything but a `buy` orders nothing.
 *
 * A line that cannot be purchased orders nothing either, whatever decision it carries. That
 * is enforced here rather than left to the UI to avoid offering the choice: a stock
 * allocation reaching a purchase order would be money spent on a movement of stock we already
 * own, and one careless call site should not be able to cause it.
 */
export function decidedQty(line: PlanLine, decision: PlanDecision | undefined): number {
  if (!line.purchasable) return 0;
  if (!decision || decision.skip) return 0;
  return decision.buy ?? 0;
}

/**
 * What one decided line costs, or `null` when it cannot be costed.
 *
 * Null is NOT zero and the two must never be added together: a line we cannot price still has
 * to be bought, it simply cannot be weighed against a budget (S10e). The totals below keep
 * them in separate counters for exactly this reason.
 */
export function decidedCost(line: PlanLine, decision: PlanDecision | undefined): number | null {
  const qty = decidedQty(line, decision);
  if (qty <= 0) return 0;
  const perUnit = m8CashImpact({
    order_qty: 1,
    unit_cost: line.unit_cost,
    unit_cost_base: line.unit_cost_base,
  });
  return perUnit === null ? null : perUnit * qty;
}

export interface PlanTotals {
  /** Lines the buyer has settled, whichever way. */
  decided: number;
  /** Lines still untouched. Reported so an unfinished pass cannot read as a finished one. */
  undecided: number;
  buying: number;
  usingStock: number;
  /** Lines resolved onto the existing PO book: nothing ordered, nothing spent (S15). */
  usingPo: number;
  skipped: number;
  /** Units across every buy decision. */
  units: number;
  /** Money for the buy decisions we CAN price. */
  cost: number;
  /** Buy decisions with no price. Counted, never summed as zero. */
  unpriced: number;
}

/**
 * Roll the decisions up. Allocations are included in the counts, because the buyer decided
 * them too, but they can never contribute money: `purchasable` is false, so `decidedQty`
 * feeds off a `buy` they cannot be given.
 */
export function planTotals(lines: PlanLine[], decisions: PlanDecisionMap): PlanTotals {
  const t: PlanTotals = {
    decided: 0, undecided: 0, buying: 0, usingStock: 0, usingPo: 0, skipped: 0,
    units: 0, cost: 0, unpriced: 0,
  };
  for (const line of lines) {
    const d = decisions[line.id];
    if (!d) {
      t.undecided += 1;
      continue;
    }
    t.decided += 1;
    // A mixture counts under every part it contains: "using stock" and "buying" are both
    // true of a 50-stock + 150-buy decision, and the tiles say "includes", not "only".
    if (d.skip) t.skipped += 1;
    if ((d.stock?.qty ?? 0) > 0) t.usingStock += 1;
    if ((d.po ?? 0) > 0) t.usingPo += 1;
    if ((d.buy ?? 0) > 0) {
      t.buying += 1;
      const qty = decidedQty(line, d);
      t.units += qty;
      const cost = decidedCost(line, d);
      if (cost === null) t.unpriced += 1;
      else t.cost += cost;
    }
  }
  return t;
}

export interface BudgetVerdict {
  /** Null until the buyer enters one. No budget is not a budget of zero. */
  budget: number | null;
  cost: number;
  /** Positive when there is room left, negative when the decisions overrun. */
  remaining: number | null;
  over: boolean;
  /** Buy decisions that could not be priced, so the verdict is incomplete by this much. */
  unpriced: number;
}

/**
 * Measure the finished decisions against a budget.
 *
 * Only called once the buyer asks. Until then there is no verdict to give, and `budget: null`
 * says so rather than implying the plan fits inside nothing.
 */
export function budgetVerdict(totals: PlanTotals, budget: number | null): BudgetVerdict {
  const hasBudget = budget !== null && Number.isFinite(budget);
  return {
    budget: hasBudget ? budget : null,
    cost: totals.cost,
    remaining: hasBudget ? (budget as number) - totals.cost : null,
    over: hasBudget ? totals.cost > (budget as number) : false,
    unpriced: totals.unpriced,
  };
}

/**
 * When the decisions overrun, which ones to drop.
 *
 * Worst-ranked first, dropping until the remainder fits: the same greedy ordering the plan
 * used to apply up front, moved to the end where it belongs. It is a PROPOSAL - each line is
 * accepted or overruled individually - so the allocator advises here instead of deciding.
 *
 * Unpriceable lines are never proposed for the cut. Dropping one saves an amount nobody can
 * state, so it cannot be justified as closing a gap.
 */
export function proposeCuts(
  lines: PlanLine[],
  decisions: PlanDecisionMap,
  budget: number | null,
): PlanLine[] {
  if (budget === null || !Number.isFinite(budget)) return [];
  const buys = lines
    .filter((l) => (decisions[l.id]?.buy ?? 0) > 0)
    .map((l) => ({ line: l, cost: decidedCost(l, decisions[l.id]) }))
    .filter((x): x is { line: PlanLine; cost: number } => x.cost !== null && x.cost > 0);

  let total = buys.reduce((s, b) => s + b.cost, 0);
  if (total <= budget) return [];

  const UNRANKED = Number.MAX_SAFE_INTEGER;
  const worstFirst = [...buys].sort(
    (a, b) => (b.line.rank ?? UNRANKED) - (a.line.rank ?? UNRANKED),
  );
  const cuts: PlanLine[] = [];
  for (const b of worstFirst) {
    if (total <= budget) break;
    cuts.push(b.line);
    total -= b.cost;
  }
  return cuts;
}

// ===========================================================================
// S16 (captain, 21 Aug, 3rd time requested): the decision is made ON the plan row -
// the backend persists it per recommendation (`POST/DELETE .../recommendations/
// {rec_id}/decision`). The functions below translate between the FE's own shape
// above and the wire shape at `types/decisions.types.ts`; nothing here is stored
// locally any more - `usePlanLines` folds the server's own list back into a
// `PlanDecisionMap` on every load (see `serverDecisionsToMap`).
// ===========================================================================

/**
 * The `kind` a decision carries, derived from which parts it has rather than stored
 * separately - it can never drift from the parts themselves. Mirrors the backend's own
 * derivation (`decision_service._validate_plan_row_decision`).
 */
export function planDecisionKind(d: PlanDecision): PlanRowDecisionKind {
  if (d.skip) return 'skip';
  const parts = [d.buy, d.stock?.qty, d.po].filter((v) => (v ?? 0) > 0).length;
  if (parts > 1) return 'mixture';
  if ((d.buy ?? 0) > 0) return 'buy';
  if ((d.stock?.qty ?? 0) > 0) return 'use_stock';
  return 'use_po';
}

/** The FE decision, as `POST .../recommendations/{rec_id}/decision` wants it. */
export function toRecordPlanRowDecisionPayload(d: PlanDecision): RecordPlanRowDecisionPayload {
  return {
    kind: planDecisionKind(d),
    buy_qty: d.buy,
    stock_takes: (d.stock?.sources ?? []).map((s) => ({ location: s.warehouse_code, qty: s.qty })),
    po_qty: d.po,
    reason_text: d.reason,
    price_mode: d.priceMode ?? DEFAULT_PRICE_MODE,
    // Omitted rather than sent empty: the backend reads "no code" as "the engine's
    // supplier stands", and an empty string would be a supplier nobody has.
    ...(d.supplierCode ? { supplier_code: d.supplierCode } : {}),
  };
}

/**
 * The server's persisted decision, folded back into the FE's own shape. The server
 * only ever stores/returns a stock take's warehouse CODE (no UUIDs surface) -
 * `resolveWarehouseId` recovers the id that code names, off the SAME free-pool source
 * list the decision was built from; a code with no match (a location the pool no
 * longer lists) falls back to the code itself, which keeps the take visible and still
 * nets correctly, scoped by code instead of id for that one entry.
 */
export function fromServerPlanDecision(
  sd: ServerPlanDecision,
  resolveWarehouseId: (code: string) => string | undefined,
): PlanDecision {
  const priced = {
    priceMode: sd.price_mode ?? DEFAULT_PRICE_MODE,
    ...(sd.supplier_code ? { supplierCode: sd.supplier_code } : {}),
    ...(sd.draft_po_number ? { confirmed: true } : {}),
  };
  if (sd.kind === 'skip') return { skip: true, ...priced };
  const out: PlanDecision = { ...priced };
  if ((sd.buy_qty ?? 0) > 0) out.buy = sd.buy_qty as number;
  const takenSources = sd.stock_takes
    .filter((t) => t.qty > 0)
    .map((t) => ({
      warehouse_id: resolveWarehouseId(t.location) ?? t.location,
      warehouse_code: t.location,
      qty: t.qty,
    }));
  const stockQty = takenSources.reduce((s, x) => s + x.qty, 0);
  if (stockQty > 0) out.stock = { qty: stockQty, sources: takenSources };
  if ((sd.po_qty ?? 0) > 0) out.po = sd.po_qty as number;
  if (sd.reason_text) out.reason = sd.reason_text;
  return out;
}

/**
 * Every persisted row decision on a run, folded into the `PlanDecisionMap` every
 * cell/tile on this screen already reads. `lines` names which product each
 * recommendation id belongs to (so a stock take's location code can be resolved
 * against that SAME product's free pool); `coverSources` is `usePlanLines`' own
 * `cover.data.sources` map, keyed by product id.
 */
/** `recommendation_id -> product_id`, built once off the run's flat (ungrouped) line
 *  list - the same lookup `serverDecisionsToMap` needs and the cache-patch functions
 *  below need too, so it lives in one place rather than three. */
export function productIdMap(lines: PlanLine[]): Map<string, string | null> {
  const map = new Map<string, string | null>();
  for (const l of lines) map.set(l.id, l.product_id);
  return map;
}

export function serverDecisionsToMap(
  serverDecisions: ServerPlanDecision[],
  lines: PlanLine[],
  coverSources: Record<string, { warehouse_id: string; warehouse_code: string }[]>,
): PlanDecisionMap {
  const productOf = productIdMap(lines);
  const map: Record<string, PlanDecision> = {};
  for (const sd of serverDecisions) {
    const productId = productOf.get(sd.recommendation_id) ?? null;
    const sources = productId ? coverSources[productId] : undefined;
    const resolve = (code: string) => sources?.find((s) => s.warehouse_code === code)?.warehouse_id;
    map[sd.recommendation_id] = fromServerPlanDecision(sd, resolve);
  }
  return map;
}

/** A recommendation id resolved to whatever counts it as "the same product" for
 *  `decided_count` purposes - the real product id when known, or (falling back
 *  safely, never silently dropping the row from the count) the recommendation id
 *  itself when the caller's line list cannot name one. */
function countingKey(recId: string, productOf: (recId: string) => string | null | undefined): string {
  return productOf(recId) ?? recId;
}

/**
 * Fold freshly-written decisions straight into the cached list (S3 perf, AC-3.5) -
 * deciding one row must not refetch the whole run's decisions.
 *
 * `decided_count` is RECOMPUTED off the merged data's distinct product set, matching
 * the server's own by-PRODUCT count (R14) exactly - not incremented per call. An
 * increment-per-write OVERcounts on a LOCATION-grain (ungrouped) run: the same
 * product decided at two different warehouses is two separate `decide()` calls (two
 * rows, never fanned out together the way a product-grain GROUP's members are), and
 * an increment-per-call reads that as two decided products where the server - and the
 * header's own "N of Total made" - counts one. Bug found in review: the header could
 * read "412 of 200 decided" on a run with heavy multi-warehouse products.
 */
export function applyDecisionWrites(
  old: PlanRowDecisionListResponse | undefined,
  writes: ServerPlanDecision[],
  productOf: (recommendationId: string) => string | null | undefined,
): PlanRowDecisionListResponse | undefined {
  if (!old || writes.length === 0) return old;
  const byId = new Map(old.data.map((d) => [d.recommendation_id, d]));
  for (const w of writes) byId.set(w.recommendation_id, w);
  const data = Array.from(byId.values());
  const decidedKeys = new Set(data.map((d) => countingKey(d.recommendation_id, productOf)));
  return {
    ...old,
    data,
    decided_count: decidedKeys.size,
  };
}

/**
 * Withdraw recs from the cached list (S3 perf, AC-3.5) - the mirror of
 * `applyDecisionWrites`. `decided_count` is recomputed the same way (see that
 * function's docstring), off whatever survives the removal.
 *
 * The server's clear pulls EVERY draft PO line the cleared rec's PRODUCT carries
 * (`decision_service._remove_product_lines`), not just the cleared rec's own line - a
 * product-grain group's OTHER members, or a location-grain row sharing the same
 * product, can lose their draft line as a side effect of clearing a different row.
 * Any surviving cached decision for that same product has its `draft_po_number` /
 * `draft_po_id` stripped here too, or the Decision pill would keep reading Confirmed
 * for a line the server already pulled (found in review).
 */
export function applyDecisionClears(
  old: PlanRowDecisionListResponse | undefined,
  recIds: string[],
  productOf: (recommendationId: string) => string | null | undefined,
): PlanRowDecisionListResponse | undefined {
  if (!old) return old;
  const clearedIds = new Set(recIds);
  const removedAny = old.data.some((d) => clearedIds.has(d.recommendation_id));
  if (!removedAny) return old;
  const clearedProducts = new Set(
    recIds
      .map((id) => productOf(id))
      .filter((p): p is string => Boolean(p)),
  );
  const data = old.data
    .filter((d) => !clearedIds.has(d.recommendation_id))
    .map((d) => {
      const pid = productOf(d.recommendation_id);
      if (pid && clearedProducts.has(pid) && (d.draft_po_number || d.draft_po_id)) {
        return { ...d, draft_po_number: null, draft_po_id: null };
      }
      return d;
    });
  const decidedKeys = new Set(data.map((d) => countingKey(d.recommendation_id, productOf)));
  return {
    ...old,
    data,
    decided_count: decidedKeys.size,
  };
}

/**
 * Whether two decisions describe the exact same mixture - same kind and quantities,
 * and (for a stock take) the same warehouses at the same quantities each. Reason text
 * and source ORDER are ignored: "5 from BRW + 1 from PJ" recorded in either order is
 * one decision, but it is NOT the same decision as "6 from BRW" even though both total
 * 6 - which bins were actually drawn on is part of what was decided.
 */
export function planDecisionsEqual(
  a: PlanDecision | undefined,
  b: PlanDecision | undefined,
): boolean {
  if (!a || !b) return a === b;
  if ((a.priceMode ?? DEFAULT_PRICE_MODE) !== (b.priceMode ?? DEFAULT_PRICE_MODE)) return false;
  if ((a.supplierCode ?? null) !== (b.supplierCode ?? null)) return false;
  if (!!a.skip !== !!b.skip) return false;
  if (a.skip) return true;
  if ((a.buy ?? 0) !== (b.buy ?? 0)) return false;
  if ((a.po ?? 0) !== (b.po ?? 0)) return false;
  const sort = (s: { warehouse_code: string; qty: number }[]) =>
    [...s].sort((x, y) => x.warehouse_code.localeCompare(y.warehouse_code));
  const aSources = sort(a.stock?.sources ?? []);
  const bSources = sort(b.stock?.sources ?? []);
  if (aSources.length !== bSources.length) return false;
  return aSources.every(
    (s, i) => s.warehouse_code === bSources[i].warehouse_code && s.qty === bSources[i].qty,
  );
}

/** What a GROUPED (product-grain) row's decision cell shows: the mixture every member
 *  agrees on, or `mixed` when they do not (some decided differently, or some decided
 *  and others have not). Nobody having decided at all is undecided, not mixed. */
export interface GroupDecisionState {
  decision: PlanDecision | undefined;
  mixed: boolean;
}

/**
 * S16: a group row is decided by fanning the SAME decision out to every member (the
 * way `updateMoq` already fans a MOQ edit out) - so its own cell shows the unanimous
 * result of that fan-out, or `mixed` when the members disagree (a fan-out that partly
 * failed, or a run that carried per-location decisions from before grouping existed).
 */
export function groupDecisionState(memberIds: string[], decisions: PlanDecisionMap): GroupDecisionState {
  const ds = memberIds.map((id) => decisions[id]);
  if (ds.every((d) => d === undefined)) return { decision: undefined, mixed: false };
  const first = ds[0];
  const allSame = ds.every((d) => planDecisionsEqual(d, first));
  return allSame ? { decision: first, mixed: false } : { decision: undefined, mixed: true };
}
