import { useCallback, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import { useHasPermission } from '@/hooks/usePermissions';
import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';
import {
  comparePull,
  confirmPull,
  discardPull,
  downloadPullXlsx,
  getCurrentPull,
  getPull,
  getPullRows,
  startPull,
  startPullErrorMessage,
} from '../services/autocountPullService';
import type {
  AutocountPull,
  AutocountPullEntity,
  AutocountPullPhase,
  AutocountPullRowsQuery,
} from '../types/autocountPull.types';

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

/** B1 (small-fix track): a stable module-level function, not an inline closure re-created
 *  on every render of every `usePull` caller - `AutocountPullReview` and
 *  `ImportJobDetailPage` both call `usePull` for the SAME job, so two independent
 *  `QueryObserver`s already exist for one query key; a fresh `refetchInterval` reference
 *  on every render is one more thing that can make either observer re-evaluate its
 *  schedule more than the 10s cadence actually calls for. */
function pullRefetchInterval(query: { state: { data?: AutocountPull } }): number | false {
  const data = query.state.data;
  const phase = data?.phase;
  if (phase === 'building' || phase === 'previewing') return 10000;
  if (phase === 'confirmed') {
    const applyStatus = data?.apply_status;
    const applyEnded = applyStatus === 'finished' || applyStatus === 'failed';
    return applyEnded ? false : 10000;
  }
  return false;
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
    refetchInterval: pullRefetchInterval,
  });
}

/** D1 (small-fix track): the pull's captured rows live on `import_job_rows` like any other
 *  importer's, so `PullChangesTab` reads them through the same shared `useImportJobRows` /
 *  `import-job-rows` query key every job detail page uses - and that hook's `staleTime` (60s)
 *  is common to every importer, not pull-specific. A rows fetch that ran while this pull was
 *  still `building`/`previewing` (or any other mount of the same key inside that window - a
 *  prior visit, a back/forward nav) can otherwise still be served once the pull reaches
 *  `review`. Invalidating the moment `phase` reaches `review` or `confirmed` closes that gap
 *  without touching the shared hook's `staleTime`. The effect's own dependency array
 *  (`[phase, jobId, queryClient]`) is ALREADY the guard against re-running on a same-phase
 *  poll tick - React skips an effect whose deps are all reference-equal to the previous
 *  render's - so a second ref tracking "the last phase seen" on top of that (N4, opus review,
 *  fix round 3) was redundant, and actively wrong on a `jobId` change: the app router keeps
 *  this component mounted across job A -> job B (prev/next navigation), and a ref keyed only
 *  on phase would have suppressed the invalidation for job B if both jobs happened to be
 *  observed in the same phase. */
export function useRefreshRowsOnReview(jobId: string, phase: AutocountPullPhase | undefined): void {
  const queryClient = useQueryClient();

  useEffect(() => {
    if (phase === 'review' || phase === 'confirmed') {
      queryClient.invalidateQueries({ queryKey: ['import-job-rows', jobId] });
    }
  }, [phase, jobId, queryClient]);
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

/** AC-DS-10: mirrors `useConfirmPull` - invalidates the pull itself plus the current-pull
 *  query (a discarded pull is no longer "open", so `GET /current` must stop finding it),
 *  toasts "Pull discarded" on success, the extracted API error message on failure.
 *
 *  S3 (Phase 3 fix round 1): also invalidates `['import-job']` (prefix form, no `id` -
 *  this hook only ever sees `pull.job_id`, not the job page's OWN `id` URL param, which
 *  E2 already notes can differ) so the generic Job Summary card and its Cancel Job
 *  button (`[id]/page.tsx`'s own `useQuery({ queryKey: ['import-job', id], ... })`)
 *  refresh too - a discard from `building`/`previewing` leaves that card showing a
 *  `canCancel` Cancel Job button and a stale status otherwise. */
export function useDiscardPull() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (jobId: string) => discardPull(jobId),
    onSuccess: (pull) => {
      queryClient.setQueryData(['autocount-pull', pull.job_id], pull);
      queryClient.invalidateQueries({ queryKey: ['autocount-pull', pull.job_id] });
      queryClient.invalidateQueries({ queryKey: ['autocount-pull-current', pull.entity] });
      queryClient.invalidateQueries({ queryKey: ['import-job'] });
      toast.success('Pull discarded');
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : 'Could not discard the pull.');
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
