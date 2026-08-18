/**
 * Plan grain - the run's stamped decision grain, read by every planning surface.
 *
 * Plan grain is ADMIN POLICY (plan section 5.1). It is not a per-run selector and
 * there is deliberately no control anywhere on the plan page that changes it: a run
 * stamps the configured grain when it is created and keeps it forever, so what the
 * buyer sees here is a fact about the run in front of them, never a choice.
 *
 * Three states, and the third is not a value of the first two:
 *
 *   - `product`  - the single product row owns the chosen quantity; the per-location
 *                  view stays open as a read and drill view (AC-F02).
 *   - `location` - the per-location recommendations and overrides stay actionable; the
 *                  product row is a read-only aggregate of them.
 *   - LEGACY     - a run created before the front-planning contract. It carries no
 *                  grain and no channel breakdown, accepts no decision in either grain,
 *                  and is never backfilled (AC-F10). A legacy run is identified by its
 *                  NULL contract version, not by a missing grain alone, because that is
 *                  the field the backend rejects writes on.
 */

export type PlanGrain = 'product' | 'location';

/** The two run fields every grain question is answered from. */
export interface RunGrainState {
  /** Stamped once at run creation. NULL only on a legacy run. */
  decision_grain?: PlanGrain | null;
  /** `1` on a front-planning run, NULL on a legacy one. */
  front_planning_contract_version?: number | null;
}

/** A run that predates the front-planning contract: read-only in both grains. */
export function isLegacyRun(run: RunGrainState | null | undefined): boolean {
  if (!run) return false;
  return (
    run.front_planning_contract_version === null ||
    run.front_planning_contract_version === undefined ||
    !run.decision_grain
  );
}

/** What the header chip says. Legacy is its own word, not an absent grain. */
export function planGrainLabel(run: RunGrainState | null | undefined): string {
  if (!run) return 'Plan grain unknown';
  if (isLegacyRun(run)) return 'Legacy run';
  return run.decision_grain === 'location' ? 'Plan grain: Location' : 'Plan grain: Product';
}

/**
 * Why a decision control is disabled, or null when it is actionable.
 *
 * `surface` is the grain the control would write in. A run answers exactly one of
 * them, so the other surface stays open for reading and says which screen owns the
 * decision instead of silently doing nothing.
 */
export function decisionLockReason(
  run: RunGrainState | null | undefined,
  surface: PlanGrain,
): string | null {
  if (!run) return null;
  if (isLegacyRun(run)) return 'Legacy run - read only. Create a new plan to decide.';
  if (run.decision_grain === surface) return null;
  return run.decision_grain === 'product'
    ? 'Decided at Product grain'
    : 'Decided at Location grain';
}
