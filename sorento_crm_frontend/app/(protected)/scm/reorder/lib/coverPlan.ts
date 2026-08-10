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
