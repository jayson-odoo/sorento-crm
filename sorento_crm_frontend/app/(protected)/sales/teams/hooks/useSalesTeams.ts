import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import {
  createSalesTeam,
  getSalesTeam,
  getSalesTeamAgentOptions,
  getSalesTeams,
  updateSalesTeam,
} from '../services/salesTeamService';
import type { SalesTeamDetail, SalesTeamSaveInput } from '../types/salesTeam.types';

export const SALES_TEAMS_KEY = ['sales-teams'] as const;
export const SALES_TEAM_KEY = ['sales-team'] as const;
export const SALES_TEAM_AGENT_OPTIONS_KEY = ['sales-team-agent-options'] as const;

export function useSalesTeams(query: string) {
  return useQuery({
    queryKey: [...SALES_TEAMS_KEY, query],
    queryFn: () => getSalesTeams(query),
    placeholderData: (previous) => previous,
  });
}

/** `on`: the date the members are read for (the Targets page's Active on); default today. */
export function useSalesTeam(id: string | null, on?: string) {
  return useQuery({
    queryKey: [...SALES_TEAM_KEY, id, on ?? null],
    queryFn: () => getSalesTeam(id as string, on),
    enabled: !!id,
    retry: 1,
  });
}

export function useSalesTeamAgentOptions(enabled = true) {
  return useQuery({
    queryKey: SALES_TEAM_AGENT_OPTIONS_KEY,
    queryFn: getSalesTeamAgentOptions,
    enabled,
    staleTime: 30_000,
  });
}

/**
 * Create a team with its agents, or rename it and set its agents - one save for both the
 * modal and the team page. The toast names anyone the save moved out of another team,
 * because that changed a second team the reader is not looking at.
 */
export function useSaveSalesTeam() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (input: SalesTeamSaveInput): Promise<SalesTeamDetail> => {
      const { teamId, name, is_active, sales_agent_ids, moves_on, leader_sales_agent_id } = input;
      const extra = {
        ...(moves_on ? { moves_on } : {}),
        // null is sent: it clears the leader (W1).
        ...(leader_sales_agent_id !== undefined ? { leader_sales_agent_id } : {}),
      };
      if (!teamId) {
        return createSalesTeam({ name, is_active, sales_agent_ids, ...extra });
      }
      // One PATCH, one transaction: a refused rename cannot leave the agents half-saved.
      return updateSalesTeam(teamId, { name, is_active, sales_agent_ids, ...extra });
    },
    onSuccess: (team, input) => {
      queryClient.invalidateQueries({ queryKey: SALES_TEAMS_KEY });
      queryClient.invalidateQueries({ queryKey: SALES_TEAM_KEY });
      queryClient.invalidateQueries({ queryKey: SALES_TEAM_AGENT_OPTIONS_KEY });
      const moved = team.moved ?? [];
      const base = input.teamId ? 'Sales team saved' : 'Sales team created';
      toast.success(
        moved.length
          ? `${base}. Moved ${moved.map((m) => `${m.label} from ${m.from_team_name}`).join(', ')}.`
          : base,
      );
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to save sales team'),
  });
}
