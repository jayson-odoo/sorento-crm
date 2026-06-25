import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  getMyCoverage,
  subscribeCoverage,
  unsubscribeCoverage,
} from '../services/coverageService';

const COVERAGE_KEY = ['coverage-subscriptions'];

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
      toast.success('Coverage removed.');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to remove coverage'),
  });
}
