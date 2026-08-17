/**
 * ============================================================================
 * SCM FRONT PLANNING (Stage 2) - FIXTURE SCENARIO SELECTOR
 * ============================================================================
 * Phase-1 fixture support ONLY. Nothing here reaches a live payload: the run
 * carries its own `decision_grain` / `front_planning_contract_version` and the
 * recommendation rows their own `project_need` / `retail_need` /
 * `unclassified_need` / `decisions_read_only`, all served by the backend
 * (S2-BE-2, S2-BE-3). The Phase-1 overlays that used to decorate those payloads
 * in `reorderRunService` are gone, as is the `?plan_mock=` URL switch that drove
 * them - a development affordance has no business being reachable from a
 * shipped URL.
 *
 * What survives is the scenario CONSTANT the two remaining Phase-1 mock stores
 * (`summaryOrderMockStore`, `poWorklistMockStore`) shape their fixtures around.
 * Both are served behind `USE_SUMMARY_ORDER_MOCKS` / `USE_PO_WORKLIST_MOCKS`,
 * which are false, and `summaryOrderMockStore`'s fixtures are what the Stage-2
 * vitest specs assert against - hence the file rather than a deletion.
 * ============================================================================
 */
import type { PlanGrain } from './planGrain';

export type FrontPlanningScenario =
  | 'product'
  | 'location'
  | 'legacy'
  | 'empty'
  | 'loading'
  | 'decision_error';

/** The scenario the fixtures are shaped around. Product is the rollout default grain. */
export const DEFAULT_SCENARIO: FrontPlanningScenario = 'product';

/** The scenario in force. A compile-time constant - nothing selects it at runtime. */
export function frontPlanningScenario(): FrontPlanningScenario {
  return DEFAULT_SCENARIO;
}

/** The grain a fixture run is stamped with under the current scenario. */
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
