/**
 * ============================================================================
 * SCM FRONT PLANNING (Stage 2) - SCENARIO SWITCH + RUN/RECOMMENDATION MOCK
 * ============================================================================
 * Phase 1 only. Phase 2 (slices S2-BE-2 and S2-BE-3) flips
 * `USE_FRONT_PLANNING_MOCKS` to false and DELETES this file; the fields it
 * overlays arrive on the real payloads instead and no component changes.
 *
 * ## The scenario switch
 *
 * Stage 2 has six states that cannot all be reached from one fixture, so ONE
 * switch selects which the whole page serves and every Stage-2 mock store reads
 * it from here. Change it by editing `DEFAULT_SCENARIO` below, or without an edit
 * by appending `?plan_mock=<scenario>` to the URL after navigating in:
 *
 *   product         a run stamped `decision_grain = product` (the rollout default).
 *                   The product row is actionable; per-location decisions are
 *                   read-only and say which screen owns them.
 *   location        a run stamped `decision_grain = location`. The mirror image:
 *                   per-location decisions actionable, the product row a read-only
 *                   aggregate.
 *   legacy          a run created before the contract: no grain, no channel
 *                   breakdown ("Unavailable"), every decision refused.
 *   empty           a completed run that froze no rows.
 *   loading         the report never resolves, so the skeleton can be inspected.
 *   decision_error  a product-grain run whose decision POST is refused with the
 *                   grain/legacy 409, so the refusal is renderable. The precision
 *                   422 needs no scenario: type `2.5` into an `EA` row.
 *
 * The switch is a Phase-1 development affordance, NOT a plan-grain selector. Plan
 * grain is admin policy (plan section 5.1) and no user-facing control sets it.
 *
 * ## What is overlaid rather than fabricated
 *
 * The plan grid runs on a real frozen run with thousands of rows, and inventing a
 * parallel set of recommendations would prove nothing about the screen. So for the
 * RUN and the RECOMMENDATIONS this store decorates the live payload with the
 * Stage-2 fields the backend does not carry yet, deterministically and by index.
 * The Summary Order Report is fully fixtured (`summaryOrderMockStore`) because its
 * worked cases - the once-only rounding of AC-F11, the `kg`/`EA` precision pair of
 * AC-F12 - are exact numbers that must be checkable by hand.
 * ============================================================================
 */
import type { PlanGrain } from './planGrain';
import type { ReorderRecommendation } from '../types/reorder.types';

/**
 * Phase-2: OFF. The run payload carries its own `decision_grain` /
 * `front_planning_contract_version` and the recommendation rows their own
 * `project_need` / `retail_need` / `unclassified_need` / `decisions_read_only`,
 * so both decorators below are pass-throughs and the scenario switch no longer
 * reaches a screen. The file survives because its fixtures are what the vitest
 * specs assert against.
 */
export const USE_FRONT_PLANNING_MOCKS = false;

export type FrontPlanningScenario =
  | 'product'
  | 'location'
  | 'legacy'
  | 'empty'
  | 'loading'
  | 'decision_error';

/** Served when the URL names no scenario. Product is the rollout default grain. */
export const DEFAULT_SCENARIO: FrontPlanningScenario = 'product';

const SCENARIOS: FrontPlanningScenario[] = [
  'product',
  'location',
  'legacy',
  'empty',
  'loading',
  'decision_error',
];

/** The scenario in force for this page view. Safe to call during SSR. */
export function frontPlanningScenario(): FrontPlanningScenario {
  if (typeof window === 'undefined') return DEFAULT_SCENARIO;
  const named = new URLSearchParams(window.location.search).get('plan_mock');
  const match = SCENARIOS.find((s) => s === named);
  return match ?? DEFAULT_SCENARIO;
}

/** The grain a run is stamped with under the current scenario. */
export function scenarioGrain(): PlanGrain | null {
  return frontPlanningScenario() === 'location' ? 'location' : 'product';
}

/** The two run fields Stage 2 adds. Both NULL on a legacy run, by contract. */
export function runGrainFields(): {
  decision_grain: PlanGrain | null;
  front_planning_contract_version: number | null;
} {
  if (frontPlanningScenario() === 'legacy') {
    return { decision_grain: null, front_planning_contract_version: null };
  }
  return { decision_grain: scenarioGrain(), front_planning_contract_version: 1 };
}

/** Decorate a run (today's run, or one from history) with its stamped grain. */
export function withRunGrain<T extends object>(run: T | null): T | null {
  if (!USE_FRONT_PLANNING_MOCKS || !run) return run;
  return { ...run, ...runGrainFields() };
}

/**
 * Decorate frozen location facts with their demand-channel split (AC-F07).
 *
 * Deterministic by ROW INDEX, never random, so two reads of the same page agree:
 * a location's own need lands in the channel its segment sells to, and every fifth
 * row moves a tenth of it into unclassified so the missing-class exception is
 * reachable. A legacy run gets NULLs, which is what renders "Unavailable".
 */
export function withChannelNeeds(recs: ReorderRecommendation[]): ReorderRecommendation[] {
  if (!USE_FRONT_PLANNING_MOCKS) return recs;
  const legacy = frontPlanningScenario() === 'legacy';
  const readOnly = scenarioGrain() === 'product';
  return recs.map((rec, index) => {
    if (legacy) {
      return {
        ...rec,
        project_need: null,
        retail_need: null,
        unclassified_need: null,
        decisions_read_only: true,
      };
    }
    const base = rec.outstanding_sales ?? 0;
    const unclassified = index % 5 === 4 ? Math.round(base * 0.1) : 0;
    const owned = Math.max(base - unclassified, 0);
    const isProject = (rec.segment ?? 'project') === 'project';
    return {
      ...rec,
      project_need: isProject ? owned : 0,
      retail_need: isProject ? 0 : owned,
      unclassified_need: unclassified,
      decisions_read_only: readOnly,
    };
  });
}
