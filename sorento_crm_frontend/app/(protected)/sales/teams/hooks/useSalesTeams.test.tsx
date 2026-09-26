/**
 * useSaveSalesTeam: a create is one POST; an edit is ONE PATCH carrying the name, Active and
 * the agents, so a refused rename cannot leave the agents half-saved (review round 1, N1).
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const service = vi.hoisted(() => ({
  createSalesTeam: vi.fn(),
  updateSalesTeam: vi.fn(),
  setSalesTeamMembers: vi.fn(),
  getSalesTeam: vi.fn(),
  getSalesTeams: vi.fn(),
  getSalesTeamAgentOptions: vi.fn(),
}));
vi.mock('../services/salesTeamService', () => service);
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { useSaveSalesTeam } from './useSalesTeams';

function wrapper({ children }: { children: React.ReactNode }) {
  return <QueryClientProvider client={new QueryClient()}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  Object.values(service).forEach((fn) => fn.mockReset());
  service.createSalesTeam.mockResolvedValue({ moved: [] });
  service.updateSalesTeam.mockResolvedValue({ moved: [] });
});

describe('useSaveSalesTeam', () => {
  it('creates with one POST', async () => {
    const { result } = renderHook(() => useSaveSalesTeam(), { wrapper });
    await act(() =>
      result.current.mutateAsync({ teamId: null, name: 'North', is_active: true, sales_agent_ids: ['a'] }),
    );
    expect(service.createSalesTeam).toHaveBeenCalledWith({
      name: 'North',
      is_active: true,
      sales_agent_ids: ['a'],
    });
  });

  it('saves an edit as one PATCH with the agents and the move date', async () => {
    const { result } = renderHook(() => useSaveSalesTeam(), { wrapper });
    await act(() =>
      result.current.mutateAsync({
        teamId: 'north',
        name: 'North East',
        is_active: false,
        sales_agent_ids: ['a', 'b'],
        moves_on: '2026-10-15',
      }),
    );
    expect(service.updateSalesTeam).toHaveBeenCalledWith('north', {
      name: 'North East',
      is_active: false,
      sales_agent_ids: ['a', 'b'],
      moves_on: '2026-10-15',
    });
    expect(service.setSalesTeamMembers).not.toHaveBeenCalled();
  });

  it('sends the leader on a create and on an edit, null clearing it (W1)', async () => {
    const { result } = renderHook(() => useSaveSalesTeam(), { wrapper });
    await act(() =>
      result.current.mutateAsync({
        teamId: null,
        name: 'North',
        is_active: true,
        sales_agent_ids: ['a'],
        leader_sales_agent_id: 'a',
      }),
    );
    expect(service.createSalesTeam).toHaveBeenCalledWith({
      name: 'North',
      is_active: true,
      sales_agent_ids: ['a'],
      leader_sales_agent_id: 'a',
    });

    await act(() =>
      result.current.mutateAsync({
        teamId: 'north',
        name: 'North',
        is_active: true,
        sales_agent_ids: ['a'],
        leader_sales_agent_id: null,
      }),
    );
    expect(service.updateSalesTeam).toHaveBeenCalledWith('north', {
      name: 'North',
      is_active: true,
      sales_agent_ids: ['a'],
      leader_sales_agent_id: null,
    });
  });
});
