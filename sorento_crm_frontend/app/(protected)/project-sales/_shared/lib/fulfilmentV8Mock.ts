/**
 * ============================================================================
 * SCM Fulfilment Planning - LADDER v8 PHASE 1 MOCK OVERLAY (S2, PLAN-scm-fulfilment-
 * feedback-2sep.md, rulings R-A/R-B/R-K)
 * ============================================================================
 * The board and stock-detail endpoints are LIVE (ladder v7.1) - this is not a fresh feature
 * behind a mock catalog, it is three fields v8's engine will add to a payload the backend
 * already sends for real. `fulfilmentPlanningService.ts` calls the three functions below on
 * every `getPlanningBoard` / `getSupply` / `getStockDetail` response to compute them
 * client-side, so Phase 1 can render and be walked in a real browser before Phase 2 writes
 * the engine change.
 *
 * THE CONTRACT PHASE 2 OWES (delete this file's callers the day it ships):
 *
 *   BoardCellLocation.available_for_project : string | null
 *     On every `site_pool` row and the "Site pool subtotal" row built from it. Computed
 *     here as `min(floor(available_qty x (100 - pool_share_pct) / 100), max(net, 0))` -
 *     `net` being THAT SAME row's own five-pool net, which ladder v7.1 already sends
 *     (`_net_fields`, `front_planning_board_service.py`). `0`, never blank, on an
 *     addressable pool row (R-K); absent on `own` / `group` / `other_group`.
 *
 *   StockDetail.five_pool_net : string | null
 *     On a `group: 'pools'` stock-detail read only. Mocked here as an ALIAS of that same
 *     read's own `available_qty`, because a `group: 'pools'` read's `available_qty` already
 *     IS the five pools' net (same `netting().pools_net()` the board row reads) - Phase 2
 *     only needs to expose it under this name so `StockDocumentsPanel` does not have to
 *     import a board-shaped type to read the cap its own query already knows.
 *
 *   BoardLadderOption.step === 'pool_share', label "Use BRW stock", first in walk order
 *     Mocked here by relabelling and moving today's `pool` step (last before Buy under
 *     v7.1's "pool LAST" rule) to the front. `gives_qty` is set only because the real
 *     engine's SHARE quantity does not exist yet: `null` when the old `pool` step already
 *     covered the unit whole (nothing more to say), `'0'` when it gave nothing (matches
 *     R-K's "a pool row with 0 to give reads 0, never blank" for the options table too).
 *     Phase 2 REPLACES `gives_qty`'s value with the real share the walk actually computed;
 *     it does not add the field, which already exists on the wire type.
 *
 * `DEFAULT_POOL_SHARE_PCT` mirrors S1's own default (`priority_policy.pool_share_pct`,
 * `FulfilmentPriorityPanel.tsx`) - Phase 2 reads the tenant's real value off that row
 * instead of this constant.
 * ============================================================================
 */
import { fromMinor, toMinor } from './supplyComposition';
import type {
  BoardCellLocation,
  BoardLadderOption,
} from '../types/fulfilmentPlanning.types';

/** What the server calls the five-pool set on `net_of` (mirrors `CellStockTable.tsx`). */
export const POOLS_SET = 'pools';

/** S1's own default (`FulfilmentPriorityPanel.tsx`), used here only until Phase 2 wires
 * the real per-tenant value through to the board and stock-detail responses. */
export const DEFAULT_POOL_SHARE_PCT = 50;

/**
 * `min(floor(availableQty x (100 - sharePct) / 100), max(fivePoolNet, 0))` - R-K's formula,
 * shared by every caller so a row, a subtotal and a ledger row can never read it three
 * different ways. `null` in, `null` out: there is nothing to share out of an unstated figure.
 */
export function mockAvailableForProject(
  availableQty: string | null | undefined,
  fivePoolNet: string | null | undefined,
  sharePct: number = DEFAULT_POOL_SHARE_PCT,
): string | null {
  if (availableQty === null || availableQty === undefined) return null;
  const shareMinor = Math.floor(
    (toMinor(availableQty) * (100 - sharePct)) / 100,
  );
  if (fivePoolNet === null || fivePoolNet === undefined) {
    return fromMinor(shareMinor);
  }
  const capMinor = Math.max(toMinor(fivePoolNet), 0);
  return fromMinor(Math.min(shareMinor, capMinor));
}

/**
 * Sets `available_for_project` on every addressable `site_pool` row of a locations array -
 * the cell's own `locations`, or one contributing line's netted `locations` (R1). Every other
 * row is returned unchanged (the field stays absent, which is what makes it render blank).
 *
 * Generic over `undefined` so a caller can pass `contribution.locations` (optional) straight
 * through without an extra guard at every call site.
 */
export function mockAugmentLocations<T extends BoardCellLocation[] | undefined>(
  locations: T,
): T {
  if (!locations) return locations;
  return locations.map((entry) =>
    (entry.where ?? 'own') === 'site_pool'
      ? {
          ...entry,
          available_for_project:
            mockAvailableForProject(entry.available_qty, entry.net) ?? '0',
        }
      : entry,
  ) as T;
}

/**
 * Reorders a line's ladder options into v8's walk order and turns today's `pool` step into
 * `pool_share`, "Use BRW stock", first (R-A). A line the pool step never fired for - it was
 * dropped for a hot-selling product under v7.1 - passes through unchanged: v8 retires that
 * gate too, but restoring a step the live payload never sent is Phase 2's job, not a mock's.
 */
export function mockReorderLadderOptionsV8(
  options: BoardLadderOption[] | null | undefined,
): BoardLadderOption[] | undefined {
  if (!options || options.length === 0) return options ?? undefined;
  const poolOption = options.find((option) => option.step === 'pool');
  if (!poolOption) return options;
  const poolShareOption: BoardLadderOption = {
    ...poolOption,
    step: 'pool_share',
    label: 'Use BRW stock',
    gives_qty: poolOption.whole ? null : '0',
  };
  const rest = options.filter((option) => option.step !== 'pool');
  return [poolShareOption, ...rest];
}
