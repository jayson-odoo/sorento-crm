import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  assignCoverage,
  getMyCoverage,
  getTeamCoverage,
  revokeCoverageById,
  subscribeCoverage,
  unsubscribeCoverage,
} from '../services/coverageService';

const COVERAGE_KEY = ['coverage-subscriptions'];
const TEAM_COVERAGE_KEY = ['team-coverage-subscriptions'];

export function useMyCoverage() {
  return useQuery({
    queryKey: COVERAGE_KEY,
    queryFn: () => getMyCoverage(),
    staleTime: 1000 * 30,
  });
}

interface CoverageMutationVars {
  targetUserId: string;
  expiresAt?: string;
  redirectAssignments?: boolean;
}

export function useSubscribeCoverage() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ targetUserId, expiresAt, redirectAssignments }: CoverageMutationVars) =>
      subscribeCoverage(targetUserId, expiresAt, redirectAssignments),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: COVERAGE_KEY });
      toast.success('Coverage added.');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to add coverage'),
  });
}

export function useUpdateCoverage() {
  const queryClient = useQueryClient();
  return useMutation({
    // Backend POST is an upsert keyed by (subscriber, target): re-posting an
    // already-covered colleague updates expires_at + redirect mode in place (and
    // reactivates).
    mutationFn: ({ targetUserId, expiresAt, redirectAssignments }: CoverageMutationVars) =>
      subscribeCoverage(targetUserId, expiresAt, redirectAssignments),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: COVERAGE_KEY });
      toast.success('Coverage updated.');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to update coverage'),
  });
}

export function useUnsubscribeCoverage() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (targetUserId: string) => unsubscribeCoverage(targetUserId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: COVERAGE_KEY });
      queryClient.invalidateQueries({ queryKey: TEAM_COVERAGE_KEY });
      toast.success('Coverage removed.');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to remove coverage'),
  });
}

// --- HoD team coverage -------------------------------------------------------

export function useTeamCoverage(enabled = true) {
  return useQuery({
    queryKey: TEAM_COVERAGE_KEY,
    queryFn: () => getTeamCoverage(),
    staleTime: 1000 * 30,
    enabled,
  });
}

interface AssignCoverageVars {
  covererId: string;
  targetUserId: string;
  expiresAt?: string;
  redirectAssignments?: boolean;
}

export function useAssignCoverage() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ covererId, targetUserId, expiresAt, redirectAssignments }: AssignCoverageVars) =>
      assignCoverage(covererId, targetUserId, expiresAt, redirectAssignments),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: TEAM_COVERAGE_KEY });
      queryClient.invalidateQueries({ queryKey: COVERAGE_KEY });
      toast.success('Coverage assigned.');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to assign coverage'),
  });
}

export function useRevokeCoverageById() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (subscriptionId: string) => revokeCoverageById(subscriptionId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: TEAM_COVERAGE_KEY });
      queryClient.invalidateQueries({ queryKey: COVERAGE_KEY });
      toast.success('Coverage revoked.');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to revoke coverage'),
  });
}
