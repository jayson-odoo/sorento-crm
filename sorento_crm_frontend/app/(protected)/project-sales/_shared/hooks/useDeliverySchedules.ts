'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  useRecordNeighbours,
  type RecordNeighboursResult,
} from '@/hooks/useRecordNeighbours';
import {
  confirmDeliveryScheduleVersion,
  DELIVERY_SCHEDULE_VERSION_NEIGHBOURS_PATH,
  dismissDeliveryScheduleColumn,
  getDeliveryScheduleVersion,
  listDeliverySchedules,
  listDeliveryScheduleVersions,
  resolveDeliveryScheduleProduct,
  retryDeliveryScheduleExtraction,
  saveDeliveryScheduleCells,
  uploadDeliverySchedule,
} from '../services/deliveryScheduleService';
import type {
  DeliveryScheduleCellInput,
  DeliveryScheduleConfirmBody,
  DeliveryScheduleUploadBody,
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
 * Prev/next within this schedule's own revision history, so a reviewer can step from R2 to
 * R1 without going back to the project tab. Newest first, the order the versions grid uses.
 */
export function useDeliveryScheduleVersionNeighbours(
  versionId: string | undefined,
  options: { enabled?: boolean } = {},
): RecordNeighboursResult {
  return useRecordNeighbours(
    DELIVERY_SCHEDULE_VERSION_NEIGHBOURS_PATH,
    options.enabled === false ? null : (versionId ?? null),
  );
}

/**
 * Upload invalidates the PROJECT too: the schedule binds delivery phases to it, so the
 * header and the phase list downstream both change once extraction lands.
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

  return { upload };
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
      toast.success('Schedule confirmed. Its phases are on the project.');
    },
    onError: (error: Error) => toast.error(error.message),
  });

  return { saveCells, resolveProduct, dismissColumn, confirm, retryExtraction };
}
