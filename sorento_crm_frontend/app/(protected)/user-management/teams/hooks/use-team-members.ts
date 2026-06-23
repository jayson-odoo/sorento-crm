import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  getTeam,
  getTeamMembers,
  getUsersSelect,
  addTeamMember,
  removeTeamMember,
  updateTeamMember,
} from '../services/teamService';
import type { TeamAddMemberPayload } from '../types/team.types';

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
  return useQuery({
    queryKey: ['user-management-users-select'],
    queryFn: () => getUsersSelect(),
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

export function useUpdateTeamMemberRoundRobin(teamId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ userId, includeInRoundRobin }: { userId: string; includeInRoundRobin: boolean }) =>
      updateTeamMember(teamId, userId, { include_in_round_robin: includeInRoundRobin }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['user-management-team-members', teamId] });
    },
    onError: (error: Error) => toast.error(error.message),
  });
}
