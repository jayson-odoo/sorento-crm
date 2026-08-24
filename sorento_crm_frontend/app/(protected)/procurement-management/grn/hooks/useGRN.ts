import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { buildDataGridParams } from '@/lib/api-client';
import {
  useRecordNeighbours,
  type RecordNeighboursResult,
} from '@/hooks/useRecordNeighbours';
import {
  getGRNs,
  getGRN,
  createGRN,
  updateGRN,
  deleteGRN,
  bulkDeleteGRNs,
  GRN_NEIGHBOURS_PATH,
  type GRNListParams,
} from '../services/grnService';
import type { GRNFormData } from '../types/grn.types';

export function useGRNs(params: GRNListParams) {
  return useQuery({
    queryKey: [
      'grn',
      params.pageIndex,
      params.pageSize,
      params.sorting,
      params.searchQuery,
      params.picking_status,
      params.inspection_status,
      params.spo_allocation_id,
    ],
    queryFn: () => getGRNs(params),
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

/**
 * Prev/next neighbours of a GRN within the active filtered+sorted list set.
 * Serializes the list query (search/sort/status filters) with `buildDataGridParams`
 * - the same serialization the list page uses - so the backend honours filters
 * identically. `page`/`limit` are sent but ignored by the neighbours endpoint.
 */
export function useGRNNeighbours(
  grnId: string | null,
  listParams: GRNListParams,
): RecordNeighboursResult {
  // Only forward filters the list GET actually honours (picking/inspection status).
  // `spo_allocation_id` is not a server-side filter on the GRN list, so it is
  // intentionally not threaded into neighbours.
  const params = buildDataGridParams(listParams, {
    picking_status: listParams.picking_status,
    inspection_status: listParams.inspection_status,
  });
  return useRecordNeighbours(GRN_NEIGHBOURS_PATH, grnId, params);
}

export function useGRN(id: string | null) {
  return useQuery({
    queryKey: ['grn', id],
    queryFn: () => {
      if (!id) throw new Error('GRN ID is required');
      return getGRN(id);
    },
    enabled: !!id,
    retry: 1,
  });
}

export function useCreateGRN() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: GRNFormData) => createGRN(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['grn'] });
      toast.success('GRN created successfully');
    },
    onError: (error: Error) =>
      toast.error(error.message || 'Failed to create GRN'),
  });
}

export function useUpdateGRN() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<GRNFormData> }) =>
      updateGRN(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['grn'] });
      queryClient.invalidateQueries({ queryKey: ['grn'] });
      toast.success('GRN updated successfully');
    },
    onError: (error: Error) =>
      toast.error(error.message || 'Failed to update GRN'),
  });
}

export function useDeleteGRN() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteGRN(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['grn'] });
      toast.success('GRN deleted successfully');
    },
    onError: (error: Error) =>
      toast.error(error.message || 'Failed to delete GRN'),
  });
}

export function useBulkDeleteGRNs() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (ids: string[]) => bulkDeleteGRNs(ids),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['grn'] });
      toast.success(
        result?.message ?? `${result?.deleted_count ?? 0} GRN(s) deleted`,
      );
    },
    onError: (error: Error) =>
      toast.error(error.message || 'Failed to bulk delete GRNs'),
  });
}
