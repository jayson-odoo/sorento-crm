/**
 * SCM engine simulation harness (dev tool) - types.
 *
 * Mirrors ``scripts/scm_sim`` on the backend: 38 frozen scenarios, a dedicated
 * ``sorento_scm_sim`` database, and two JSON files (the last run, the blessed
 * reference). See ``app/api/v1/scm/simulation.py`` for the endpoints and
 * ``services/simulationService.ts`` for the request/response contract.
 */

/** How this scenario's last run compares to the blessed baseline. */
export type ScenarioStatus = 'SAME' | 'CHANGED' | 'NEW' | 'GONE' | 'NO_BASELINE';

/** One of the groups a diff can fall into (compare.py's own grouping, never re-derived
 *  client-side). */
export type ChangedGroup =
  | 'quantity suggestion'
  | 'price advice'
  | 'level suggestion'
  | 'cover composition'
  | 'disposition'
  | 'order summary'
  | 'other';

/** The grid-relevant slice of a scenario's first recommendation, or null when the
 *  scenario produced none (a legitimate outcome for some scenarios). */
export interface ScenarioRecSummary {
  rec_type: string | null;
  recommended_qty: number | null;
  rounded_qty: number | null;
  triggered_reason: string | null;
  cash_impact: number | null;
}

/** "SO" (Sales Order, dealer segment) or "OI" (Order Inquiry, project segment) - which
 *  demand feed a scenario's committed figure came from (M8 engine target model). */
export type DemandLabel = 'SO' | 'OI';

/** What the engine actually SAW for this scenario - read off the current run's snapshot
 *  (falling back to the blessed baseline), not the ScenarioSpec it was seeded from. The
 *  grid's input-side columns, mirroring the real Reorder Planning row's On hand / SO /
 *  SPO / PO figures so the two screens read the same way. */
export interface ScenarioInputs {
  on_hand: number | null;
  committed: number | null;
  spo_incoming: number | null;
  /** Informational only (ADR/migration 337 - never nets against demand); 0, never null,
   *  when no recommendation carried one. */
  po_open: number;
  demand_label: DemandLabel;
}

export interface ScenarioRow {
  code: string;
  title: string;
  segment: string;
  policy: string;
  expected_note: string;
  inputs: ScenarioInputs;
  current: ScenarioRecSummary | null;
  baseline: ScenarioRecSummary | null;
  status: ScenarioStatus;
  changed_groups: ChangedGroup[];
}

export interface ScenarioDiffEntry {
  path: string;
  old: unknown;
  new: unknown;
  group: ChangedGroup;
}

/** Full field-level diff for one scenario, plus its whole current/baseline snapshot
 *  blob so the detail panel can show the frozen inputs without a second fetch. */
export interface ScenarioDiff {
  code: string;
  status: ScenarioStatus;
  diffs: ScenarioDiffEntry[];
  current: Record<string, unknown> | null;
  baseline: Record<string, unknown> | null;
}

export interface SimulationOverview {
  sim_db_active: boolean;
  baseline_exists: boolean;
  baseline_blessed_at: string | null;
  current_exists: boolean;
  current_run_at: string | null;
  latest_run_id: string | null;
  scenario_count: number;
}

export interface RunSimulationResult {
  run_id: string;
  blessed: boolean;
  buy_count: number;
  disposition_count: number;
  exception_count: number;
  total_cash_impact: number;
  recommendation_count: number;
}

export interface BlessBaselineResult {
  blessed: true;
  baseline_blessed_at: string | null;
}
