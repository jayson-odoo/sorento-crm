import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';
import {
  comparePull,
  confirmPull,
  downloadPullXlsx,
  getCurrentPull,
  getPull,
  getPullRows,
  startPull,
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

/** The caller's open pull for this entity, or `null`. Drives the button label (AC-PL-5). */
export function useCurrentPull(entity: AutocountPullEntity) {
  return useQuery({
    queryKey: ['autocount-pull-current', entity],
    queryFn: () => getCurrentPull(entity),
    staleTime: 1000 * 15,
    retry: 1,
  });
}

/** Polls every 10s while `building` or `previewing` (AC-BD-6); stops on every other phase. */
export function usePull(jobId: string, enabled = true) {
  return useQuery({
    queryKey: ['autocount-pull', jobId],
    queryFn: () => getPull(jobId),
    enabled: enabled && Boolean(jobId),
    staleTime: 1000 * 5,
    retry: 1,
    refetchInterval: (query) => {
      const phase = query.state.data?.phase;
      return phase === 'building' || phase === 'previewing' ? 10000 : false;
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
