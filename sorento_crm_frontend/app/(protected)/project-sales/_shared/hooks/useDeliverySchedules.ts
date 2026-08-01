'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  confirmDeliveryScheduleVersion,
  getDeliveryScheduleVersion,
  listDeliverySchedules,
  listDeliveryScheduleVersions,
  resolveDeliveryScheduleProduct,
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

  return { saveCells, resolveProduct, confirm };
}
