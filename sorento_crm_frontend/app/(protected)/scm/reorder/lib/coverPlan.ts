/**
 * Buy it, cover it from stock we already hold, or both.
 *
 * > "the use stock is use from BRW, not from BRW-IB ... you need to suggest me also, whether
 * >  to buy or use stock, if half half also need to suggest, and also need to suggest use
 * >  stock from where"
 *
 * Mirrors `app/services/scm/cover_service.py`. The rule it enforces is that a line's OWN
 * on-hand is never a source: it is already inside the net position, so offering it back would
 * count the same units twice. Cover means stock at ANOTHER location.
 *
 * ## Why the allocation runs here and not on the server
 *
 * The free pool is shared. Two lines for the same product draw on the same units, so as soon
 * as one line is decided the other's options shrink. The server hands over the pool once,
 * whole; this module spends it down as decisions accumulate, which is the only place that
 * knows what has been decided so far.
 */

export interface CoverSource {
  warehouse_id: string;
  warehouse_code: string;
  segment: string | null;
  qty: number;
}

export interface CoverSourceUse extends CoverSource {
  /** Dealer stock serving project demand, or the reverse. Offered, never silently mixed. */
  cross_segment: boolean;
}

export interface CoverProposal {
  coverQty: number;
  buyQty: number;
  sources: CoverSourceUse[];
  /** Neither whole answer is right: cover what exists and buy the rest. */
  isSplit: boolean;
}

export const NO_COVER: CoverProposal = {
  coverQty: 0,
  buyQty: 0,
  sources: [],
  isSplit: false,
};

/** What each warehouse has already given away to earlier decisions in this pass. */
export type TakenByWarehouse = Readonly<Record<string, number>>;

export function proposeCover(
  shortage: number,
  lineWarehouseId: string | null,
  lineSegment: string | null,
  free: CoverSource[] | undefined,
  taken: TakenByWarehouse = {},
): CoverProposal {
  if (!(shortage > 0)) return NO_COVER;

  const candidates: CoverSourceUse[] = [];
  for (const s of free ?? []) {
    // Its own stock is already netted. Offering it back is the bug this replaces.
    if (lineWarehouseId && s.warehouse_id === lineWarehouseId) continue;
    const remaining = s.qty - (taken[s.warehouse_id] ?? 0);
    if (remaining <= 0) continue;
    candidates.push({
      ...s,
      qty: remaining,
      cross_segment: Boolean(lineSegment && s.segment && s.segment !== lineSegment),
    });
  }

  // Same segment first, then biggest. Crossing the dealer/project boundary is a decision the
  // business tracks, so it is the fallback rather than the first answer.
  candidates.sort(
    (a, b) =>
      Number(a.cross_segment) - Number(b.cross_segment) ||
      b.qty - a.qty ||
      a.warehouse_code.localeCompare(b.warehouse_code),
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
  return { coverQty: covered, buyQty, sources: used, isSplit: covered > 0 && buyQty > 0 };
}

/**
 * The suggestion in words.
 *
 * Deliberately a sentence rather than a code: the buyer is being asked to agree with a
 * recommendation, and "Use 6 from BRW-BB and buy 182" can be agreed with at a glance where a
 * pair of numbers in separate columns cannot.
 */
export function describeCover(proposal: CoverProposal, fmt: (n: number) => string): string {
  const { coverQty, buyQty, sources } = proposal;
  if (coverQty <= 0 && buyQty <= 0) return 'Nothing to do';
  const from = sources.map((s) => `${fmt(s.qty)} from ${s.warehouse_code}`).join(', ');
  if (coverQty > 0 && buyQty > 0) return `Use ${from}, and buy ${fmt(buyQty)}`;
  if (coverQty > 0) return `Use ${from}`;
  return `Buy ${fmt(buyQty)}`;
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
): CoverProposal {
  if (line.status === 'covered_by_stock') {
    const committed = line.rec.covered_committed ?? line.order_qty;
    const available = Math.max(0, line.rec.covered_available ?? 0);
    if (!(committed > 0)) return NO_COVER;
    const covered = Math.min(committed, available);
    const buyQty = Math.max(0, committed - covered);
    if (covered <= 0) return { coverQty: 0, buyQty, sources: [], isSplit: false };
    return {
      coverQty: covered,
      buyQty,
      sources: [
        {
          warehouse_id: line.warehouse_id ?? '',
          warehouse_code: line.rec.warehouse_code ?? line.warehouse,
          segment: line.rec.segment ?? null,
          qty: covered,
          cross_segment: false,
        },
      ],
      isSplit: covered > 0 && buyQty > 0,
    };
  }
  return proposeCover(Math.ceil(line.order_qty), line.warehouse_id, line.rec.segment ?? null, free, taken);
}
