/**
 * salesTargetService: the contract with /api/v1/sales/targets (plan 16.3). Paths, methods and
 * bodies are asserted because a key typo is a silently dropped field on the backend, not an
 * error (LESSONS-LEARNT). Modelled on `sales/teams/services/salesTeamService.test.ts`.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const apiFetch = vi.hoisted(() => vi.fn());
vi.mock('@/lib/api', () => ({ apiFetch }));

import {
  createSalesTarget,
  createTargetChild,
  deleteSalesTarget,
  duplicateSalesTarget,
  getSalesTarget,
  getSalesTargetOptions,
  getSalesTargets,
  patchSalesTarget,
  patchSalesTargetPeriod,
} from './salesTargetService';

function ok(body: unknown) {
  return { ok: true, status: 200, json: async () => body } as Response;
}

beforeEach(() => apiFetch.mockReset());

describe('salesTargetService', () => {
  it('lists with on, subject, sales_team_id and query', async () => {
    apiFetch.mockResolvedValue(ok({ on: '2026-10-15', rows: [], unassigned_amount: 0, no_team_count: 0 }));
    await getSalesTargets({ on: '2026-10-15', subject: 'agent' });
    expect(apiFetch).toHaveBeenLastCalledWith('/api/v1/sales/targets?on=2026-10-15&subject=agent');

    await getSalesTargets({ on: '2026-10-15', subject: 'agent', salesTeamId: 'none' });
    expect(apiFetch).toHaveBeenLastCalledWith(
      '/api/v1/sales/targets?on=2026-10-15&subject=agent&sales_team_id=none',
    );

    await getSalesTargets({ on: '2026-10-15', subject: 'team', query: 'north' });
    expect(apiFetch).toHaveBeenLastCalledWith(
      '/api/v1/sales/targets?on=2026-10-15&subject=team&query=north',
    );
  });

  it('reads one target, on a date when given', async () => {
    apiFetch.mockResolvedValue(ok({ id: 't1' }));
    await getSalesTarget('t1');
    expect(apiFetch).toHaveBeenLastCalledWith('/api/v1/sales/targets/t1');
    await getSalesTarget('t1', '2026-10-15');
    expect(apiFetch).toHaveBeenLastCalledWith('/api/v1/sales/targets/t1?on=2026-10-15');
  });

  it('reads options', async () => {
    apiFetch.mockResolvedValue(ok({ agents: [], teams: [], categories: [] }));
    await getSalesTargetOptions();
    expect(apiFetch).toHaveBeenCalledWith('/api/v1/sales/targets/options');
  });

  it('creates an agent target with the S1-19 payload', async () => {
    apiFetch.mockResolvedValue(ok({ id: 't1' }));
    const payload = {
      subject_kind: 'agent' as const,
      sales_agent_id: 'a1',
      name: 'North FY26 H2',
      metric: 'amount' as const,
      basis: 'ordered' as const,
      product_scope: 'all' as const,
      start_date: '2026-10-01',
      end_date: '2026-12-31',
      target_value: 120000,
    };
    await createSalesTarget(payload);
    expect(apiFetch).toHaveBeenCalledWith('/api/v1/sales/targets', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  });

  it('creates a team target with agent_figures, never a bare target_value', async () => {
    apiFetch.mockResolvedValue(ok({ id: 't1' }));
    const payload = {
      subject_kind: 'team' as const,
      sales_team_id: 'north',
      name: 'North Team Target',
      metric: 'amount' as const,
      basis: 'ordered' as const,
      product_scope: 'all' as const,
      start_date: '2026-10-01',
      end_date: '2026-10-31',
      agent_figures: [{ sales_agent_id: 'a1', target_value: 500 }],
    };
    await createSalesTarget(payload);
    expect(apiFetch).toHaveBeenLastCalledWith('/api/v1/sales/targets', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  });

  it('patches the header, a period, adds a child, duplicates and deletes', async () => {
    apiFetch.mockResolvedValue(ok({ id: 't1' }));

    await patchSalesTarget('t1', { name: 'Renamed' });
    expect(apiFetch).toHaveBeenLastCalledWith('/api/v1/sales/targets/t1', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: 'Renamed' }),
    });

    await patchSalesTargetPeriod('t1', 'p1', { target_value: 250 });
    expect(apiFetch).toHaveBeenLastCalledWith('/api/v1/sales/targets/t1/periods/p1', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ target_value: 250 }),
    });

    await createTargetChild('t1', { sales_agent_id: 'b1', target_value: 300 });
    expect(apiFetch).toHaveBeenLastCalledWith('/api/v1/sales/targets/t1/children', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sales_agent_id: 'b1', target_value: 300 }),
    });

    await duplicateSalesTarget('t1');
    expect(apiFetch).toHaveBeenLastCalledWith('/api/v1/sales/targets/t1/duplicate', { method: 'POST' });

    apiFetch.mockResolvedValueOnce(ok({}));
    await deleteSalesTarget('t1');
    expect(apiFetch).toHaveBeenLastCalledWith('/api/v1/sales/targets/t1', { method: 'DELETE' });
  });

  it('throws the server message on failure', async () => {
    apiFetch.mockResolvedValue(
      new Response(JSON.stringify({ message: 'End date is before the start date.' }), {
        status: 422,
        headers: { 'content-type': 'application/json' },
      }),
    );
    await expect(
      createSalesTarget({
        subject_kind: 'agent', sales_agent_id: 'a1', name: 'ZZT', metric: 'amount', basis: 'ordered',
        product_scope: 'all', start_date: '2026-12-31', end_date: '2026-10-01', target_value: 1,
      }),
    ).rejects.toThrow(/before the start date/);
  });
});
