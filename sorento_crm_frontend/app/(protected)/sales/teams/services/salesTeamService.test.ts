/**
 * salesTeamService: the contract with /api/v1/sales/teams (plan 3.8, UAC S6-1, S6-2, S6-3,
 * S6-14). Paths, methods and bodies are asserted because a key typo is a silently dropped
 * field on the backend, not an error (LESSONS-LEARNT).
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const apiFetch = vi.hoisted(() => vi.fn());
vi.mock('@/lib/api', () => ({ apiFetch }));

import {
  createSalesTeam,
  getSalesTeam,
  getSalesTeamAgentOptions,
  getSalesTeams,
  setSalesTeamMembers,
  updateSalesTeam,
} from './salesTeamService';

function ok(body: unknown) {
  return { ok: true, status: 200, json: async () => body } as Response;
}

beforeEach(() => apiFetch.mockReset());

describe('salesTeamService', () => {
  it('lists teams with the search query', async () => {
    apiFetch.mockResolvedValue(ok({ data: [], pagination: { total: 0 }, empty: true }));
    await getSalesTeams('nor');
    expect(apiFetch).toHaveBeenCalledWith('/api/v1/sales/teams?query=nor');
  });

  it('lists teams without a query string when the search is blank', async () => {
    apiFetch.mockResolvedValue(ok({ data: [] }));
    await getSalesTeams('  ');
    expect(apiFetch).toHaveBeenCalledWith('/api/v1/sales/teams');
  });

  it('reads one team, on a date when given', async () => {
    apiFetch.mockResolvedValue(ok({ id: 't1' }));
    await getSalesTeam('t1');
    expect(apiFetch).toHaveBeenLastCalledWith('/api/v1/sales/teams/t1');
    await getSalesTeam('t1', '2026-10-15');
    expect(apiFetch).toHaveBeenLastCalledWith('/api/v1/sales/teams/t1?on=2026-10-15');
  });

  it('reads the agent options', async () => {
    apiFetch.mockResolvedValue(ok({ data: [{ id: 'a' }] }));
    expect(await getSalesTeamAgentOptions()).toEqual([{ id: 'a' }]);
    expect(apiFetch).toHaveBeenCalledWith('/api/v1/sales/teams/agent-options');
  });

  it('creates, renames and sets members with the documented bodies', async () => {
    apiFetch.mockResolvedValue(ok({ id: 't1' }));

    await createSalesTeam({ name: 'North', sales_agent_ids: ['a'], is_active: true, moves_on: '2026-10-15' });
    expect(apiFetch).toHaveBeenLastCalledWith('/api/v1/sales/teams', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: 'North', sales_agent_ids: ['a'], is_active: true, moves_on: '2026-10-15' }),
    });

    await updateSalesTeam('t1', { name: 'North East', is_active: false });
    expect(apiFetch).toHaveBeenLastCalledWith('/api/v1/sales/teams/t1', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: 'North East', is_active: false }),
    });

    await setSalesTeamMembers('t1', { sales_agent_ids: ['a', 'b'], moves_on: '2026-10-15' });
    expect(apiFetch).toHaveBeenLastCalledWith('/api/v1/sales/teams/t1/members', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sales_agent_ids: ['a', 'b'], moves_on: '2026-10-15' }),
    });
  });

  it('throws the server message on failure', async () => {
    apiFetch.mockResolvedValue(
      new Response(JSON.stringify({ message: 'A sales team called "North" already exists.' }), {
        status: 409,
        headers: { 'content-type': 'application/json' },
      }),
    );
    await expect(createSalesTeam({ name: 'North', sales_agent_ids: [] })).rejects.toThrow(
      /already exists/,
    );
  });
});
