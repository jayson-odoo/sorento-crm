'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useRouter } from 'next/navigation';
import { toast } from '@/lib/toast';
import {
  acceptRevisionProposal,
  confirmDeliveryScheduleVersion,
  deleteDeliverySchedule,
  deleteDeliveryScheduleVersion,
  dismissDeliveryScheduleColumn,
  getDeliveryScheduleVersion,
  listDeliverySchedules,
  listDeliveryScheduleVersions,
  rejectRevisionProposal,
  resolveDeliveryScheduleProduct,
  retryDeliveryScheduleExtraction,
  saveDeliveryScheduleCells,
  uploadDeliverySchedule,
} from '../services/deliveryScheduleService';
import type {
  DeliveryScheduleCellInput,
  DeliveryScheduleConfirmBody,
  DeliveryScheduleUploadBody,
  DeliveryScheduleVersion,
} from '../types/deliverySchedule.types';
import { isExtractionPending, resolveExtractionPhase } from '../types/deliverySchedule.types';
import { PROJECTS_KEY, projectKey } from './useProjects';

export const SCHEDULES_KEY = 'project-delivery-schedules';

export const schedulesKey = (projectId: string) => [SCHEDULES_KEY, 'list', projectId];
export const scheduleVersionsKey = (scheduleId: string) => [
  SCHEDULES_KEY,
  'versions',
  scheduleId,
];
export const scheduleVersionKey = (versionId: string) => [
  SCHEDULES_KEY,
  'version',
  versionId,
];

export function useDeliverySchedules(projectId: string | undefined) {
  return useQuery({
    queryKey: schedulesKey(projectId ?? ''),
    queryFn: () => listDeliverySchedules(projectId as string),
    enabled: Boolean(projectId),
  });
}

export function useDeliveryScheduleVersions(scheduleId: string | undefined) {
  return useQuery({
    queryKey: scheduleVersionsKey(scheduleId ?? ''),
    queryFn: () => listDeliveryScheduleVersions(scheduleId as string),
    enabled: Boolean(scheduleId),
  });
}

/**
 * One version, polled while the extractor is still reading it.
 *
 * The upload returns `202` with `extraction_state: "queued"`, so the review screen opens on
 * a version that has no grid yet. Polling stops the moment the state leaves queued/running,
 * including on `failed` and `partial`: there is nothing more coming and a spinner that never
 * ends reads as a broken page rather than as a failed extraction.
 */
export function useDeliveryScheduleVersion(
  versionId: string | undefined,
  options: { enabled?: boolean } = {},
) {
  return useQuery({
    queryKey: scheduleVersionKey(versionId ?? ''),
    queryFn: () => getDeliveryScheduleVersion(versionId as string),
    enabled: Boolean(versionId) && options.enabled !== false,
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data) return false;
      return isExtractionPending(resolveExtractionPhase(data)) ? 3000 : false;
    },
  });
}


/**
 * The full version this one revises, for the was -> now diff (section 9.1).
 *
 * Dates travel on the version itself (`promoted_delivery_date`), so only the QUANTITIES
 * need this: there is no such field for them, so the prior version has to be fetched in
 * full and diffed client-side. Disabled on a version 1, which revises nothing, and while
 * the version list has not yet said which id is one before this one.
 */
export function useDeliverySchedulePriorVersion(
  version: DeliveryScheduleVersion | undefined,
  options: { enabled?: boolean } = {},
) {
  const enabled =
    options.enabled !== false && Boolean(version) && (version?.version_no ?? 0) > 1;
  const versions = useDeliveryScheduleVersions(
    enabled ? version?.delivery_schedule_id : undefined,
  );
  const priorVersionId = versions.data?.find(
    (candidate) => candidate.version_no === (version?.version_no ?? 0) - 1,
  )?.id;
  const prior = useDeliveryScheduleVersion(priorVersionId, {
    enabled: enabled && Boolean(priorVersionId),
  });

  return {
    data: prior.data,
    isLoading: enabled && (versions.isLoading || (Boolean(priorVersionId) && prior.isLoading)),
    isError: prior.isError,
  };
}

/**
 * Upload invalidates the PROJECT too: the schedule binds delivery phases to it, so the
 * header and the phase list downstream both change once extraction lands.
 *
 * Delete does the same, for the same reason in reverse: removing a schedule (or the
 * version that bound them) can take delivery phases with it.
 *
 * `ConfirmDeleteDialog` raises the toast for both deletes, so neither mutation raises its
 * own - a second notification for one press is noise.
 */
export function useDeliveryScheduleMutations(projectId: string) {
  const queryClient = useQueryClient();
  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: [SCHEDULES_KEY] });
    queryClient.invalidateQueries({ queryKey: projectKey(projectId) });
  };

  const upload = useMutation({
    mutationFn: ({ poId, body }: { poId: string; body: DeliveryScheduleUploadBody }) =>
      uploadDeliverySchedule(poId, body),
    onSuccess: (result) => {
      invalidate();
      toast.success(
        `Uploaded as version ${result.version_no}. Reading the document now.`,
      );
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const remove = useMutation({
    mutationFn: (scheduleId: string) => deleteDeliverySchedule(scheduleId),
    onSuccess: invalidate,
  });

  const removeVersion = useMutation({
    mutationFn: (versionId: string) => deleteDeliveryScheduleVersion(versionId),
    onSuccess: invalidate,
  });

  return { upload, remove, removeVersion };
}

/**
 * Cell edits, column resolution and confirm.
 *
 * Every one of these returns the recomputed version, so the cache is SET from the response
 * rather than invalidated: a re-fetch would blank the grid for a moment on each keystroke's
 * save, and the reviewer is reading three numbers off it while they work.
 */
export function useDeliveryScheduleVersionMutations(
  projectId: string,
  versionId: string,
) {
  const queryClient = useQueryClient();
  const router = useRouter();

  const adopt = (version: Awaited<ReturnType<typeof getDeliveryScheduleVersion>>) => {
    queryClient.setQueryData(scheduleVersionKey(versionId), version);
    queryClient.invalidateQueries({ queryKey: schedulesKey(projectId) });
  };

  const saveCells = useMutation({
    mutationFn: (cells: DeliveryScheduleCellInput[]) =>
      saveDeliveryScheduleCells(versionId, cells),
    onSuccess: adopt,
    onError: (error: Error) => toast.error(error.message),
  });

  const resolveProduct = useMutation({
    mutationFn: ({
      productIndex,
      productId,
    }: {
      productIndex: number;
      productId: string;
    }) => resolveDeliveryScheduleProduct(versionId, productIndex, productId),
    onSuccess: adopt,
    onError: (error: Error) => toast.error(error.message),
  });

  /**
   * Overrule one column's failing check, or put it back under it.
   *
   * The response carries the recomputed verdict for the whole version, so `adopt` is what
   * moves the column out of the blocking list and the count with it.
   */
  const dismissColumn = useMutation({
    mutationFn: ({
      columnIndex,
      dismissed,
      reason,
    }: {
      columnIndex: number;
      dismissed: boolean;
      reason?: string | null;
    }) => dismissDeliveryScheduleColumn(versionId, columnIndex, dismissed, reason),
    onSuccess: adopt,
    onError: (error: Error) => toast.error(error.message),
  });

  /**
   * Read the same version again.
   *
   * `adopt` puts the version back on `queued`, which is what turns the poll back on, so
   * the screen goes from the failure card straight to the progress card.
   */
  const retryExtraction = useMutation({
    mutationFn: () => retryDeliveryScheduleExtraction(versionId),
    onSuccess: (version) => {
      adopt(version);
      toast.success('Reading this schedule again');
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const confirm = useMutation({
    mutationFn: (body: DeliveryScheduleConfirmBody) =>
      confirmDeliveryScheduleVersion(versionId, body),
    onSuccess: (version) => {
      adopt(version);
      queryClient.invalidateQueries({ queryKey: projectKey(projectId) });
      queryClient.invalidateQueries({ queryKey: [PROJECTS_KEY, 'list'] });
      // The confirm went through, but a schedule confirmed on top of an already-built sales
      // order leaves that order stale - the server says so with a preview link rather than
      // this screen guessing which order it was.
      if (version.amendment_preview_url) {
        const previewUrl = version.amendment_preview_url;
        toast.success('Schedule confirmed - the linked sales order needs an amendment.', {
          action: { label: 'Review the amendment', onClick: () => router.push(previewUrl) },
        });
      } else {
        toast.success('Schedule confirmed. Its phases are on the project.');
      }
    },
    onError: (error: Error) => toast.error(error.message),
  });

  /**
   * Accept writes the override for every cell the proposal names; reject writes nothing and
   * only marks the state. Both toast on success AND failure - unlike the cell/product saves
   * above, this is a whole re-date decision, not a keystroke.
   */
  const acceptProposal = useMutation({
    mutationFn: (index: number) => acceptRevisionProposal(versionId, index),
    onSuccess: (version) => {
      adopt(version);
      toast.success('Proposal accepted. The dates are written onto the schedule.');
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const rejectProposal = useMutation({
    mutationFn: (index: number) => rejectRevisionProposal(versionId, index),
    onSuccess: (version) => {
      adopt(version);
      toast.success('Proposal rejected.');
    },
    onError: (error: Error) => toast.error(error.message),
  });

  return {
    saveCells,
    resolveProduct,
    dismissColumn,
    confirm,
    retryExtraction,
    acceptProposal,
    rejectProposal,
  };
}
