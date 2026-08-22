/**
 * ============================================================================
 * SCM engine simulation harness (dev tool) - feature service
 * ============================================================================
 * Layering: hooks (useSimulation) → THIS service → lib/api-client → backend.
 *
 * Wraps the ``scripts/scm_sim`` CLI harness (38 frozen scenarios, a dedicated
 * ``sorento_scm_sim`` database, two JSON files) so a run/bless/diff cycle needs no
 * shell. See ``app/api/v1/scm/simulation.py`` + ``app/services/scm/simulation_service.py``.
 *
 * ── BACKEND CONTRACT ────────────────────────────────────────────────────────
 *
 * All reads work off the two JSON files on disk regardless of which database this
 * backend process happens to be connected to - they render identically whether or
 * not `sim_db_active` is true. Only the two writes (run, bless) are gated.
 *
 * 1) GET /api/v1/scm/simulation/overview
 *    → 200 { sim_db_active, baseline_exists, baseline_blessed_at, current_exists,
 *            current_run_at, latest_run_id, scenario_count }
 *    Auth: scm.dashboard.view.
 *
 * 2) GET /api/v1/scm/simulation/scenarios
 *    → 200 { data: ScenarioRow[] }  (always all 38 rows, keyed by the registry)
 *    Auth: scm.dashboard.view.
 *
 * 3) GET /api/v1/scm/simulation/scenarios/{code}/diff
 *    → 200 ScenarioDiff  (404 for an unknown code)
 *    Auth: scm.dashboard.view.
 *
 * 4) POST /api/v1/scm/simulation/run   body { bless_baseline: boolean }
 *    → 200 RunSimulationResult
 *    → 409 when this backend process is not connected to the sim database.
 *    Auth: scm.reorder.run.
 *
 * 5) POST /api/v1/scm/simulation/bless
 *    → 200 BlessBaselineResult
 *    → 400 when there is no current run to bless.
 *    Auth: scm.reorder.run.
 * ============================================================================
 */
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type {
  BlessBaselineResult,
  RunSimulationResult,
  ScenarioDiff,
  ScenarioRow,
  SimulationOverview,
} from '../types/simulation.types';

export async function getOverview(): Promise<SimulationOverview> {
  const res = await apiFetch('/api/v1/scm/simulation/overview');
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load the simulation overview'));
  return res.json();
}

export async function getScenarios(): Promise<ScenarioRow[]> {
  const res = await apiFetch('/api/v1/scm/simulation/scenarios');
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load scenarios'));
  const body = (await res.json()) as { data?: ScenarioRow[] };
  return body.data ?? [];
}

export async function getScenarioDiff(code: string): Promise<ScenarioDiff> {
  const res = await apiFetch(`/api/v1/scm/simulation/scenarios/${encodeURIComponent(code)}/diff`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load the scenario diff'));
  return res.json();
}

export async function runSimulation(blessBaseline: boolean): Promise<RunSimulationResult> {
  const res = await apiFetch('/api/v1/scm/simulation/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ bless_baseline: blessBaseline }),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to run the simulation'));
  return res.json();
}

export async function blessBaseline(): Promise<BlessBaselineResult> {
  const res = await apiFetch('/api/v1/scm/simulation/bless', { method: 'POST' });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to bless the baseline'));
  return res.json();
}
