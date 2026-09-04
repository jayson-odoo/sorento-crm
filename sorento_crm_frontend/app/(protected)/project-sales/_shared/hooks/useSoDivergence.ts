'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import {
  getDivergence,
  ingestSalesOrderFile,
  listDivergences,
  resolveDivergenceRow,
} from '../services/soDivergenceService';
import type {
  DivergenceListParams,
  DivergenceResolution,
} from '../types/soDivergence.types';
import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';

export const DIVERGENCE_LIST_KEY = 'project-so-divergences';
export const DIVERGENCE_KEY = 'project-so-divergence';
/** The sales order query, so the amend button unlocks the moment the last row is answered. */
export const SALES_ORDER_KEY = 'project-sales-order';

export const divergenceListKey = (params: DivergenceListParams) => [
  DIVERGENCE_LIST_KEY,
  params,
];

export function useDivergences(params: DivergenceListParams = {}) {
  return useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: divergenceListKey(params),
    queryFn: () => listDivergences(params),
  });
}

export function useDivergence(divergenceId: string | undefined) {
  return useQuery({
    queryKey: [DIVERGENCE_KEY, divergenceId],
    queryFn: () => getDivergence(divergenceId as string),
    enabled: Boolean(divergenceId),
  });
}

/**
 * The open reconciliation for one sales order, or none.
 *
 * Keyed on the order's `updated_at` so it refetches the moment a publish or an ingest
 * changes the order: the banner it feeds is what disables the amend button, and a stale
 * one either blocks an order that is now clean or lets a wrong amendment through.
 */
export function useOpenDivergenceForOrder(
  psoId: string | undefined,
  updatedAt?: string | null,
) {
  const query = useQuery({
    queryKey: [DIVERGENCE_LIST_KEY, 'for-order', psoId, updatedAt ?? ''],
    queryFn: () => listDivergences({ status: 'open', limit: 100 }),
    enabled: Boolean(psoId),
  });
  const open = query.data?.data.find((row) => row.project_sales_order_id === psoId);
  return { ...query, divergence: open };
}

export function useDivergenceMutations(divergenceId?: string) {
  const queryClient = useQueryClient();

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: [DIVERGENCE_LIST_KEY] });
    queryClient.invalidateQueries({ queryKey: [DIVERGENCE_KEY] });
    queryClient.invalidateQueries({ queryKey: [SALES_ORDER_KEY] });
  };

  /**
   * An unmatched or ambiguous export is a SUCCESS at the transport level and a failure at
   * the business one, so it resolves rather than throws and the toast says which.
   */
  const ingestFile = useMutation({
    mutationFn: (file: File) => ingestSalesOrderFile(file),
    onSuccess: (result) => {
      invalidate();
      if (result.outcome === 'divergent') {
        toast.warning(
          `${result.differing_count} difference${result.differing_count === 1 ? '' : 's'} against AutoCount. Reconcile them before amending.`,
        );
      } else if (result.outcome === 'matched') {
        toast.success('AutoCount agrees with this sales order.');
      } else {
        toast.error(result.message || 'That export could not be matched to a sales order.');
      }
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const resolveRow = useMutation({
    mutationFn: ({
      rowId,
      resolution,
      reason,
    }: {
      rowId: string;
      resolution: DivergenceResolution;
      reason: string;
    }) => resolveDivergenceRow(divergenceId as string, rowId, resolution, reason),
    onSuccess: (detail, variables) => {
      invalidate();
      if (detail.status === 'resolved') {
        toast.success(
          detail.corrective_publish_required
            ? 'Reconciled. A corrective file is ready to send back to AutoCount.'
            : 'Reconciled. This sales order can be amended again.',
        );
      } else {
        toast.success(
          variables.resolution === 'accept_theirs'
            ? 'AutoCount accepted for this row.'
            : 'Our value kept for this row.',
        );
      }
    },
    onError: (error: Error) => toast.error(error.message),
  });

  return { ingestFile, resolveRow };
}
