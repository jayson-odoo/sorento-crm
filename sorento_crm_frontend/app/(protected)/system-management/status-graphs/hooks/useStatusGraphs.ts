'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import {
  createStatus,
  createTransition,
  deleteStatus,
  deleteTransition,
  getStatusGraph,
  listStatusEntities,
  migrateStatusRecords,
  updateStatus,
  updateTransition,
} from '../services/statusGraphService';
import type {
  StatusCreateBody,
  StatusUpdateBody,
  TransitionCreateBody,
  TransitionUpdateBody,
} from '../types/statusGraph.types';

export const STATUS_ENTITIES_KEY = ['status-entities'];

export const statusGraphKey = (entityType: string, scopeId?: string | null) => [
  'status-graph',
  entityType,
  scopeId ?? null,
];

export function useStatusEntities() {
  return useQuery({ queryKey: STATUS_ENTITIES_KEY, queryFn: listStatusEntities });
}

export function useStatusGraph(
  entityType: string | undefined,
  scopeId?: string | null,
  withCounts = true,
) {
  return useQuery({
    queryKey: statusGraphKey(entityType ?? '', scopeId),
    queryFn: () => getStatusGraph(entityType as string, { scopeId, withCounts }),
    enabled: Boolean(entityType),
  });
}

/**
 * Every write invalidates the whole graph rather than patching one row.
 *
 * That is deliberate: the server re-validates graph-level invariants on each save
 * (exactly one starting state, no outgoing edges from a final state) and a delete
 * cascades its edges. Optimistically patching a single row would leave the rest of
 * the screen showing a graph the server has already rejected or reshaped.
 */
function useGraphMutation<TArgs, TResult>(
  mutationFn: (args: TArgs) => Promise<TResult>,
  entityType: string | undefined,
  scopeId: string | null | undefined,
  successMessage: string,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: statusGraphKey(entityType ?? '', scopeId) });
      toast.success(successMessage);
    },
    onError: (error: Error) => toast.error(error.message),
  });
}

export function useCreateStatus(entityType?: string, scopeId?: string | null) {
  return useGraphMutation<StatusCreateBody, unknown>(
    createStatus,
    entityType,
    scopeId,
    'Status created',
  );
}

export function useUpdateStatus(entityType?: string, scopeId?: string | null) {
  return useGraphMutation<{ id: string; body: StatusUpdateBody }, unknown>(
    ({ id, body }) => updateStatus(id, body),
    entityType,
    scopeId,
    'Status updated',
  );
}

export function useDeleteStatus(entityType?: string, scopeId?: string | null) {
  return useGraphMutation<string, unknown>(deleteStatus, entityType, scopeId, 'Status deleted');
}

export function useMigrateStatusRecords(entityType?: string, scopeId?: string | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, toStatusId }: { id: string; toStatusId: string }) =>
      migrateStatusRecords(id, toStatusId),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: statusGraphKey(entityType ?? '', scopeId) });
      toast.success(
        result.migrated === 1
          ? '1 record moved to the new status'
          : `${result.migrated} records moved to the new status`,
      );
    },
    onError: (error: Error) => toast.error(error.message),
  });
}

export function useCreateTransition(entityType?: string, scopeId?: string | null) {
  return useGraphMutation<TransitionCreateBody, unknown>(
    createTransition,
    entityType,
    scopeId,
    'Transition created',
  );
}

export function useUpdateTransition(entityType?: string, scopeId?: string | null) {
  return useGraphMutation<{ id: string; body: TransitionUpdateBody }, unknown>(
    ({ id, body }) => updateTransition(id, body),
    entityType,
    scopeId,
    'Transition updated',
  );
}

export function useDeleteTransition(entityType?: string, scopeId?: string | null) {
  return useGraphMutation<string, unknown>(
    deleteTransition,
    entityType,
    scopeId,
    'Transition deleted',
  );
}
