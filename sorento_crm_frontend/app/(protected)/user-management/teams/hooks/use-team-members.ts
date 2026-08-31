import { useCompany } from '@/app/providers/CompanyProvider';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useEntityMutation } from '@/hooks/useEntityMutation';
import { toast } from 'sonner';
import {
  getTeam,
  getTeamMembers,
  getUsersSelect,
  addTeamMember,
  removeTeamMember,
  updateTeamMember,
} from '../services/teamService';
import type { TeamAddMemberPayload, TeamMember } from '../types/team.types';

export function useTeam(teamId: string | null) {
  return useQuery({
    queryKey: ['user-management-team', teamId],
    queryFn: () => (teamId ? getTeam(teamId) : Promise.reject(new Error('No team ID'))),
    enabled: !!teamId,
  });
}

export function useTeamMembers(teamId: string | null) {
  return useQuery({
    queryKey: ['user-management-team-members', teamId],
    queryFn: () => (teamId ? getTeamMembers(teamId) : Promise.reject(new Error('No team ID'))),
    enabled: !!teamId,
  });
}

export function useUsersSelect() {
  // Team membership requires a grant for the team's company (AC-G1), so the picker
  // must not offer users who cannot be added - the only outcome there is an error.
  const { activeCompany } = useCompany();
  return useQuery({
    queryKey: ['user-management-users-select', activeCompany?.id ?? null],
    queryFn: () => getUsersSelect({ company_id: activeCompany?.id }),
    staleTime: 60 * 1000,
  });
}

export function useAddTeamMember(teamId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: TeamAddMemberPayload) => addTeamMember(teamId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['user-management-team-members', teamId] });
      toast.success('Member added');
    },
    onError: (error: Error) => toast.error(error.message),
  });
}

export function useRemoveTeamMember(teamId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (userId: string) => removeTeamMember(teamId, userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['user-management-team-members', teamId] });
      toast.success('Member removed');
    },
    onError: (error: Error) => toast.error(error.message),
  });
}

/**
 * The round-robin switch on a member row. Optimistic (S7-01): the switch moves
 * on press instead of waiting out the write and the member list's refetch.
 */
export function useUpdateTeamMemberRoundRobin(teamId: string) {
  return useEntityMutation<{ userId: string; includeInRoundRobin: boolean }, TeamMember>({
    mutationFn: ({ userId, includeInRoundRobin }) =>
      updateTeamMember(teamId, userId, { include_in_round_robin: includeInRoundRobin }),
    keys: [['user-management-team-members', teamId]],
    matchRow: (row, variables) => row.user_id === variables.userId,
    patchRow: (variables) => ({ include_in_round_robin: variables.includeInRoundRobin }),
    errorMessage: 'Could not change round-robin',
  });
}
