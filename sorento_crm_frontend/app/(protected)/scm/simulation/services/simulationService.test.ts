import { describe, it, expect, vi, beforeEach } from 'vitest';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));

import {
  blessBaseline,
  getOverview,
  getScenarioDiff,
  getScenarios,
  runSimulation,
} from './simulationService';

function ok(body: unknown) {
  return {
    ok: true,
    headers: { get: () => 'application/json' },
    json: async () => body,
  } as unknown as Response;
}

function failed(status: number, body: unknown) {
  return {
    ok: false,
    status,
    headers: { get: () => 'application/json' },
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as unknown as Response;
}

function calledUrl(): URL {
  const calls = apiFetch.mock.calls;
  const raw = String(calls[calls.length - 1][0]);
  return new URL(raw, 'http://x');
}

function lastInit(): RequestInit {
  const calls = apiFetch.mock.calls;
  return (calls[calls.length - 1][1] ?? {}) as RequestInit;
}

beforeEach(() => apiFetch.mockReset());

describe('simulationService - getOverview', () => {
  it('GETs the overview endpoint', async () => {
    apiFetch.mockResolvedValue(
      ok({
        sim_db_active: true,
        baseline_exists: true,
        baseline_blessed_at: '2026-08-01T00:00:00+00:00',
        current_exists: true,
        current_run_at: '2026-08-01T00:00:00+00:00',
        latest_run_id: 'run-1',
        scenario_count: 38,
      }),
    );
    const body = await getOverview();
    expect(calledUrl().pathname).toBe('/api/v1/scm/simulation/overview');
    expect(body.scenario_count).toBe(38);
    expect(body.sim_db_active).toBe(true);
  });

  it('throws the extracted error message on failure', async () => {
    apiFetch.mockResolvedValue(failed(500, { message: 'boom' }));
    await expect(getOverview()).rejects.toThrow('boom');
  });
});

describe('simulationService - getScenarios', () => {
  it('GETs the scenarios endpoint and unwraps `data`', async () => {
    apiFetch.mockResolvedValue(ok({ data: [{ code: 'SIM-P001' }] }));
    const rows = await getScenarios();
    expect(calledUrl().pathname).toBe('/api/v1/scm/simulation/scenarios');
    expect(rows).toEqual([{ code: 'SIM-P001' }]);
  });

  it('defaults to an empty array when `data` is missing', async () => {
    apiFetch.mockResolvedValue(ok({}));
    const rows = await getScenarios();
    expect(rows).toEqual([]);
  });
});

describe('simulationService - getScenarioDiff', () => {
  it('GETs the per-scenario diff endpoint, URL-encoding the code', async () => {
    apiFetch.mockResolvedValue(ok({ code: 'SIM-P001', status: 'SAME', diffs: [] }));
    await getScenarioDiff('SIM-P001');
    expect(calledUrl().pathname).toBe('/api/v1/scm/simulation/scenarios/SIM-P001/diff');
  });

  it('surfaces a 404 as a thrown error', async () => {
    apiFetch.mockResolvedValue(failed(404, { message: "Unknown scenario 'SIM-NOPE'." }));
    await expect(getScenarioDiff('SIM-NOPE')).rejects.toThrow("Unknown scenario 'SIM-NOPE'.");
  });
});

describe('simulationService - runSimulation', () => {
  it('POSTs bless_baseline and returns the run summary', async () => {
    apiFetch.mockResolvedValue(
      ok({
        run_id: 'run-1',
        blessed: false,
        buy_count: 5,
        disposition_count: 1,
        exception_count: 0,
        total_cash_impact: 1000,
        recommendation_count: 6,
      }),
    );
    const result = await runSimulation(false);
    expect(calledUrl().pathname).toBe('/api/v1/scm/simulation/run');
    expect(lastInit().method).toBe('POST');
    expect(JSON.parse(String(lastInit().body))).toEqual({ bless_baseline: false });
    expect(result.recommendation_count).toBe(6);
  });

  it('sends bless_baseline: true when requested', async () => {
    apiFetch.mockResolvedValue(
      ok({
        run_id: 'run-1',
        blessed: true,
        buy_count: 0,
        disposition_count: 0,
        exception_count: 0,
        total_cash_impact: 0,
        recommendation_count: 0,
      }),
    );
    await runSimulation(true);
    expect(JSON.parse(String(lastInit().body))).toEqual({ bless_baseline: true });
  });

  it('surfaces the 409 guard as a thrown error', async () => {
    apiFetch.mockResolvedValue(
      failed(409, { message: 'This backend is not connected to the sim database.' }),
    );
    await expect(runSimulation(false)).rejects.toThrow(
      'This backend is not connected to the sim database.',
    );
  });
});

describe('simulationService - blessBaseline', () => {
  it('POSTs to /bless with no body', async () => {
    apiFetch.mockResolvedValue(ok({ blessed: true, baseline_blessed_at: '2026-08-01T00:00:00+00:00' }));
    const result = await blessBaseline();
    expect(calledUrl().pathname).toBe('/api/v1/scm/simulation/bless');
    expect(lastInit().method).toBe('POST');
    expect(result.blessed).toBe(true);
  });

  it('surfaces the 400 (no current run) as a thrown error', async () => {
    apiFetch.mockResolvedValue(
      failed(400, { message: 'Run a simulation first - there is no current run to bless.' }),
    );
    await expect(blessBaseline()).rejects.toThrow(
      'Run a simulation first - there is no current run to bless.',
    );
  });
});
