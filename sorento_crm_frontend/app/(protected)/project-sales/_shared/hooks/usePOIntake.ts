'use client';

import * as React from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  acceptPOAnnotation,
  approvePurchaseOrder,
  confirmPOVersion,
  countersignPurchaseOrder,
  editPOAnnotation,
  getPOVersion,
  listPOVersions,
  rejectPOAnnotation,
  retryPOExtraction,
  updatePOVersionHeader,
  updatePOVersionLine,
  uploadPurchaseOrderDocument,
} from '../services/poIntakeService';
import type {
  POAnnotationEditBody,
  POIntakeController,
  POLineUpdateBody,
  POUploadBody,
  POVersion,
  POVersionHeader,
} from '../types/poIntake.types';
import { resolveExtractionPhase } from '../types/poIntake.types';
import { POS_KEY, projectKey, PROJECTS_KEY } from './useProjects';

export const PO_VERSION_KEY = 'project-po-version';
export const PO_VERSIONS_KEY = 'project-po-versions';

export const poVersionKey = (versionId: string) => [PO_VERSION_KEY, versionId];
export const poVersionsKey = (poId: string) => [PO_VERSIONS_KEY, poId];

/** How often the confirm screen asks whether extraction has finished. */
const POLL_MS = 3000;

/**
 * One PO document version.
 *
 * Polls only while extraction is queued or running. A finished version is static: its
 * extracted JSON and lines are the record of what the document said and never change on
 * their own, so polling past `done` would be noise on a 52 line payload.
 */
export function usePOVersion(versionId: string | undefined, enabled = true) {
  return useQuery({
    queryKey: poVersionKey(versionId ?? ''),
    queryFn: () => getPOVersion(versionId as string),
    enabled: Boolean(versionId) && enabled,
    refetchInterval: (query) => {
      const state = query.state.data?.extraction_state;
      return state === 'queued' || state === 'running' ? POLL_MS : false;
    },
  });
}

/** Null means the backend has no version list endpoint yet, not "no documents". */
export function usePOVersions(poId: string | undefined, enabled = true) {
  return useQuery({
    queryKey: poVersionsKey(poId ?? ''),
    queryFn: () => listPOVersions(poId as string),
    enabled: Boolean(poId) && enabled,
    retry: false,
  });
}

/**
 * Uploading a PO document.
 *
 * Invalidates the POs list and the project: a first PO moves the funnel to PO Received, so
 * the header and the board column change with it, exactly as the manual create path does.
 */
export function usePOUpload(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: POUploadBody) => uploadPurchaseOrderDocument(projectId, body),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: [POS_KEY, projectId] });
      queryClient.invalidateQueries({ queryKey: projectKey(projectId) });
      queryClient.invalidateQueries({ queryKey: [PROJECTS_KEY, 'list'] });
      queryClient.invalidateQueries({
        queryKey: poVersionsKey(result.purchase_order_id),
      });
    },
    onError: (error: Error) => toast.error(error.message),
  });
}

/**
 * Everything the confirm screen can do to one version, behind the single seam the mock
 * scenarios also satisfy. The UI never knows which one it is holding.
 */
export function usePOIntakeController(
  versionId: string | undefined,
  options: { enabled?: boolean } = {},
): POIntakeController {
  const enabled = options.enabled ?? true;
  const queryClient = useQueryClient();
  const query = usePOVersion(versionId, enabled);
  const version = query.data ?? null;
  const poId = version?.purchase_order_id;

  const [savingLineIds, setSavingLineIds] = React.useState<string[]>([]);
  const [savingAnnotationIds, setSavingAnnotationIds] = React.useState<string[]>([]);

  const key = poVersionKey(versionId ?? '');

  /** A write that hands back the whole version saves a round trip; otherwise refetch. */
  const settle = React.useCallback(
    (next: POVersion | null) => {
      if (next) {
        queryClient.setQueryData(key, next);
        return;
      }
      queryClient.invalidateQueries({ queryKey: key });
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [queryClient, versionId],
  );

  const invalidatePo = React.useCallback(() => {
    queryClient.invalidateQueries({ queryKey: key });
    if (poId) queryClient.invalidateQueries({ queryKey: poVersionsKey(poId) });
    queryClient.invalidateQueries({ queryKey: [POS_KEY] });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queryClient, poId, versionId]);

  /**
   * Header fields save on their own: a person fixing a misread PO number is not editing 52
   * lines, and blurring one field must not resubmit the others.
   */
  const headerMutation = useMutation({
    mutationFn: (body: Partial<POVersionHeader>) =>
      updatePOVersionHeader(versionId as string, body),
    onSuccess: (next) => {
      settle(next);
      toast.success('Header saved');
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const confirmMutation = useMutation({
    mutationFn: () => confirmPOVersion(versionId as string),
    onSuccess: (next) => {
      settle(next);
      invalidatePo();
      toast.success('Confirmed. These lines are now the PO.');
    },
    onError: (error: Error) => toast.error(error.message),
  });

  /**
   * Re-read the same version.
   *
   * `settle` puts the version back on `queued`, which is what turns polling back on, so the
   * screen goes straight from the failure card to the progress card without a refetch.
   */
  const retryMutation = useMutation({
    mutationFn: () => retryPOExtraction(versionId as string),
    onSuccess: (next) => {
      settle(next);
      if (poId) queryClient.invalidateQueries({ queryKey: poVersionsKey(poId) });
      toast.success('Reading this document again');
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const approveMutation = useMutation({
    mutationFn: () => approvePurchaseOrder(poId as string),
    onSuccess: () => {
      invalidatePo();
      toast.success('Purchase order approved');
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const countersignMutation = useMutation({
    mutationFn: () => countersignPurchaseOrder(poId as string),
    onSuccess: () => {
      invalidatePo();
      toast.success('Purchase order countersigned');
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const updateLine = React.useCallback(
    async (lineId: string, body: POLineUpdateBody) => {
      if (!versionId) return;
      setSavingLineIds((current) => [...current, lineId]);
      try {
        settle(await updatePOVersionLine(versionId, lineId, body));
      } catch (error) {
        toast.error(error instanceof Error ? error.message : 'Could not save this line');
        // Reload so the cell shows what the server holds rather than a value it refused.
        queryClient.invalidateQueries({ queryKey: key });
      } finally {
        setSavingLineIds((current) => current.filter((id) => id !== lineId));
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [versionId, settle, queryClient],
  );

  const runAnnotation = React.useCallback(
    async (annotationId: string, action: () => Promise<void>, success: string) => {
      setSavingAnnotationIds((current) => [...current, annotationId]);
      try {
        await action();
        queryClient.invalidateQueries({ queryKey: key });
        toast.success(success);
      } catch (error) {
        toast.error(error instanceof Error ? error.message : 'Could not record this');
      } finally {
        setSavingAnnotationIds((current) => current.filter((id) => id !== annotationId));
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [queryClient, versionId],
  );

  const acceptAnnotation = React.useCallback(
    (annotationId: string, note?: string | null) =>
      runAnnotation(
        annotationId,
        () => acceptPOAnnotation(annotationId, note),
        'Note accepted and applied',
      ),
    [runAnnotation],
  );

  const editAnnotation = React.useCallback(
    (annotationId: string, body: POAnnotationEditBody) =>
      runAnnotation(
        annotationId,
        () => editPOAnnotation(annotationId, body),
        'Your reading was applied',
      ),
    [runAnnotation],
  );

  const rejectAnnotation = React.useCallback(
    (annotationId: string, note: string) =>
      runAnnotation(
        annotationId,
        () => rejectPOAnnotation(annotationId, note),
        'Note rejected. Nothing was applied.',
      ),
    [runAnnotation],
  );

  const phase = resolveExtractionPhase(version);

  return {
    version,
    phase,
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
    isPolling:
      version?.extraction_state === 'queued' || version?.extraction_state === 'running',
    savingLineIds,
    savingAnnotationIds,
    isConfirming: confirmMutation.isPending,
    isStamping: approveMutation.isPending || countersignMutation.isPending,
    isSavingHeader: headerMutation.isPending,
    isRetrying: retryMutation.isPending,
    retryExtraction: async () => {
      if (!versionId) return;
      await retryMutation.mutateAsync().catch(() => undefined);
    },
    updateHeader: async (body) => {
      if (!versionId) return;
      await headerMutation.mutateAsync(body).catch(() => undefined);
    },
    updateLine,
    confirm: async () => {
      await confirmMutation.mutateAsync().catch(() => undefined);
    },
    acceptAnnotation,
    editAnnotation,
    rejectAnnotation,
    approve: async () => {
      if (!poId) return;
      await approveMutation.mutateAsync().catch(() => undefined);
    },
    countersign: async () => {
      if (!poId) return;
      await countersignMutation.mutateAsync().catch(() => undefined);
    },
  };
}
