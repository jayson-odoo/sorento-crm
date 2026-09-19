import { useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import { useHasPermission } from '@/hooks/usePermissions';
import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';
import {
  comparePull,
  confirmPull,
  downloadPullXlsx,
  getCurrentPull,
  getPull,
  getPullRows,
  startPull,
  startPullErrorMessage,
} from '../services/autocountPullService';
import type { AutocountPull, AutocountPullEntity, AutocountPullRowsQuery } from '../types/autocountPull.types';

/**
 * Starts (or, per the service's own reuse rule, re-attaches to) a pull. Success is the caller
 * navigating to the pull's page - which is itself the feedback - so this stays a thin wrapper;
 * an error toast needs the start-specific error-code mapping (`startPullErrorMessage`), so it
 * is left to the call site (the list's button) rather than duplicated here.
 */
export function useStartPull() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (entity: AutocountPullEntity) => startPull(entity),
    onSuccess: (pull) => {
      queryClient.setQueryData(['autocount-pull', pull.job_id], pull);
      queryClient.invalidateQueries({ queryKey: ['autocount-pull-current', pull.entity] });
    },
  });
}

/** The caller's open pull for this entity, or `null`. Drives the button label (AC-PL-5).
 *  `enabled` (captain ruling, Phase 3 fix round, V-2) gates the query itself - a caller
 *  without the entity's permission must never fire `GET /current` at all, not just hide
 *  the button that would have used the result. */
export function useCurrentPull(entity: AutocountPullEntity, enabled = true) {
  return useQuery({
    queryKey: ['autocount-pull-current', entity],
    queryFn: () => getCurrentPull(entity),
    enabled,
    staleTime: 1000 * 15,
    retry: 1,
  });
}

/** Polls every 10s while `building` or `previewing` (AC-BD-6), AND while `confirmed` with
 *  its apply job not yet in a terminal state (fix round 3, item 2) - the apply task's own
 *  `stock_list_not_archived` warning lands on the pull's metadata only once the apply task
 *  actually runs, after `phase` has already flipped to `confirmed`, so stopping the poll
 *  the instant Confirm returns would mean that warning never reaches the screen. Stops once
 *  the apply job reaches `finished`/`failed`, and on every other phase. */
export function usePull(jobId: string, enabled = true) {
  return useQuery({
    queryKey: ['autocount-pull', jobId],
    queryFn: () => getPull(jobId),
    enabled: enabled && Boolean(jobId),
    staleTime: 1000 * 5,
    retry: 1,
    refetchInterval: (query) => {
      const data = query.state.data;
      const phase = data?.phase;
      if (phase === 'building' || phase === 'previewing') return 10000;
      if (phase === 'confirmed') {
        const applyStatus = data?.apply_status;
        const applyEnded = applyStatus === 'finished' || applyStatus === 'failed';
        return applyEnded ? false : 10000;
      }
      return false;
    },
  });
}

export function usePullRows(jobId: string, params: AutocountPullRowsQuery, enabled = true) {
  return useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: ['autocount-pull-rows', jobId, params.pageIndex, params.pageSize, params.query],
    queryFn: () => getPullRows(jobId, params),
    enabled: enabled && Boolean(jobId),
    staleTime: 1000 * 30,
    retry: 1,
  });
}

export function useDownloadPullXlsx() {
  return useMutation({
    mutationFn: (jobId: string) => downloadPullXlsx(jobId),
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : 'Could not download the file.');
    },
  });
}

export function useComparePull(jobId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ filename, rows }: { filename: string; rows: Record<string, unknown>[] }) =>
      comparePull(jobId, filename, rows),
    onSuccess: (result) => {
      queryClient.setQueryData(['autocount-pull', jobId], (prev: AutocountPull | undefined) =>
        prev ? { ...prev, compare: result.summary } : prev,
      );
      queryClient.invalidateQueries({ queryKey: ['autocount-pull', jobId] });
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : 'Could not compare the file.');
    },
  });
}

export function useConfirmPull() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (jobId: string) => confirmPull(jobId),
    onSuccess: (pull) => {
      queryClient.setQueryData(['autocount-pull', pull.job_id], pull);
      queryClient.invalidateQueries({ queryKey: ['autocount-pull', pull.job_id] });
      queryClient.invalidateQueries({ queryKey: ['autocount-pull-current', pull.entity] });
      toast.success('Confirmed. Applying now.');
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : 'Could not confirm the pull.');
    },
  });
}

export interface AutocountPullAction {
  /** Gated on the permission alone (AC-PL-1) - never on whether the current-pull read has
   *  resolved, so the button either exists or does not the moment permissions are known. */
  visible: boolean;
  /** "Pull from AutoCount" with no open pull, "Review pull" once one exists (AC-PL-5). */
  label: string;
  /** With an open pull: navigates straight to it, no `startPull` call. Otherwise: starts one
   *  and navigates to the new job, or toasts the mapped refusal (AC-PL-6). */
  onSelect: () => Promise<void>;
}

/**
 * The Products list / Stock Balance grid's "Pull from AutoCount" secondary action, shared so
 * both own one gate and one click behaviour instead of an inline copy each.
 */
export function useAutocountPullAction(
  entity: AutocountPullEntity,
  permissionSlug: string,
): AutocountPullAction {
  const visible = useHasPermission(permissionSlug);
  const router = useRouter();
  const { data: currentPull } = useCurrentPull(entity, visible);
  const startMutation = useStartPull();

  const label = currentPull ? 'Review pull' : 'Pull from AutoCount';

  const onSelect = useCallback(async () => {
    if (currentPull) {
      router.push(`/system-management/import-jobs/${currentPull.job_id}`);
      return;
    }
    try {
      const pull = await startMutation.mutateAsync(entity);
      router.push(`/system-management/import-jobs/${pull.job_id}`);
    } catch (error) {
      toast.error(startPullErrorMessage(error));
    }
  }, [currentPull, entity, router, startMutation]);

  return { visible, label, onSelect };
}
