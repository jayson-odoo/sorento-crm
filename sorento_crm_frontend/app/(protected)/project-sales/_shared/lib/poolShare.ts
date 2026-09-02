/**
 * The site pool's project share, on the client (LADDER v8, R-K).
 *
 * `PLAN-scm-fulfilment-feedback-2sep.md` S2: a site pool keeps `pool_share_pct` of itself
 * back for dealers, and what is left is what a project line may take - the number the walk's
 * own step 0 asked the pool for and the number the lightbox prints as "Available for
 * Project".
 *
 * THE SERVER STATES IT WHEREVER THERE IS A ROW TO STATE IT ON: every `site_pool` row of a
 * cell arrives with `available_for_project` already computed
 * (`front_planning_engine.available_for_project`, called by the board). This module exists
 * for the two places that have no row to read it off:
 *
 *   - the Stock tab's pool SUBTOTAL, which is the share of the pool's own NET - a figure
 *     that belongs to the SET rather than to any bin, so no row carries it;
 *   - the expanded ledger's running column, whose balances the client computes as it walks
 *     the documents (`StockDocumentsPanel`), so the server never sees them.
 *
 * Both apply the SAME arithmetic the engine did, with the tenant's own `pool_share_pct` off
 * the payload (`PlanningBoard.pool_share_pct`, `StockDetail.pool_share_pct`) rather than a
 * constant, so a policy change on the Policies page moves every one of these numbers at once.
 */
import { fromMinor, QTY_SCALE, toMinor } from './supplyComposition';

/** What the server calls the five-pool set on `net_of` and on `stock-detail`'s `group`. */
export const POOLS_SET = 'pools';

/**
 * The share to assume when the payload states none - the same default the policy row carries
 * (`priority.FULFILMENT_SETTINGS_DEFAULTS.pool_share_pct`). Reached only by a payload written
 * before the field existed; every live board sends its own.
 */
export const DEFAULT_POOL_SHARE_PCT = 50;

/**
 * `min(floor(available x (100 - sharePct) / 100), max(fivePoolNet, 0))` - WHOLE units,
 * because nobody ships half of one ("BRW 47 free reads 23", R-K), and never more than the
 * pile actually nets (R-D). A negative Available spares nothing rather than a negative
 * share, the same reading `front_planning_engine.available_for_project` takes of it.
 *
 * `null` in, `null` out: there is nothing to share out of an unstated figure. A pool with
 * nothing to give answers `'0'`, which is an answer and not a blank (R-K).
 */
export function availableForProject(
  availableQty: string | null | undefined,
  fivePoolNet: string | null | undefined,
  sharePct: number | null | undefined = DEFAULT_POOL_SHARE_PCT,
): string | null {
  if (availableQty === null || availableQty === undefined) return null;
  const share = Math.min(Math.max(sharePct ?? DEFAULT_POOL_SHARE_PCT, 0), 100);
  // INTEGER arithmetic, in minor units, in the order the server does it (review round 1,
  // S2): `floor(minor x (100 - share) / 100)` and only then down to whole units. Dividing
  // by the scale first and multiplying by a float share is where 90 at 30 % read 62 on the
  // client and 63 on the server - one unit, on the number a planner is deciding against.
  const spare = Math.floor(
    Math.floor((Math.max(toMinor(availableQty), 0) * (100 - share)) / 100) / QTY_SCALE,
  ) * QTY_SCALE;
  if (fivePoolNet === null || fivePoolNet === undefined) return fromMinor(spare);
  return fromMinor(Math.min(spare, Math.max(toMinor(fivePoolNet), 0)));
}
