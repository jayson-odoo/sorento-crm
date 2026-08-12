import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { buildDataGridParams } from '@/lib/api-client';
import {
  useRecordNeighbours,
  type RecordNeighboursResult,
} from '@/hooks/useRecordNeighbours';
import {
  getPackingLists,
  getPackingList,
  createPackingList,
  updatePackingList,
  deletePackingList,
  bulkDeletePackingLists,
  PACKING_LIST_NEIGHBOURS_PATH,
  getClearanceCheckpoints,
  type PackingListsListParams,
} from '../services/packingListService';
import type { PackingListFormData } from '../types/packingList.types';

/**
 * Prev/next neighbours of a packing list within the active filtered+sorted list set.
 * Serializes the list query (search/sort/supplier/status) with `buildDataGridParams`
 * — the same serialization the list page uses — so the backend honours filters
 * identically. `page`/`limit` are sent but ignored by the neighbours endpoint.
 */
export function usePackingListNeighbours(
  packingListId: string | null,
  listParams: PackingListsListParams,
): RecordNeighboursResult {
  const params = buildDataGridParams(listParams, {
    supplier_id: listParams.supplier_id,
    shipment_status: listParams.shipment_status,
  });
  return useRecordNeighbours(PACKING_LIST_NEIGHBOURS_PATH, packingListId, params);
}

export function usePackingLists(params: PackingListsListParams) {
  return useQuery({
    queryKey: [
      'packing-lists',
      params.pageIndex,
      params.pageSize,
      params.sorting,
      params.searchQuery,
      params.supplier_id,
      params.shipment_status,
    ],
    queryFn: () => getPackingLists(params),
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

export function usePackingList(id: string | null) {
  return useQuery({
    queryKey: ['packing-list', id],
    queryFn: () => {
      if (!id) throw new Error('Packing list ID is required');
      return getPackingList(id);
    },
    enabled: !!id,
    retry: 1,
  });
}

export function useCreatePackingList() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: PackingListFormData) => createPackingList(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['packing-lists'] });
      toast.success('Packing list created successfully');
    },
    onError: (error: Error) =>
      toast.error(error.message || 'Failed to create packing list'),
  });
}

export function useUpdatePackingList() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      data,
    }: {
      id: string;
      data: Partial<PackingListFormData>;
    }) => updatePackingList(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['packing-lists'] });
      queryClient.invalidateQueries({ queryKey: ['packing-list'] });
      toast.success('Packing list updated successfully');
    },
    onError: (error: Error) =>
      toast.error(error.message || 'Failed to update packing list'),
  });
}

export function useDeletePackingList() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deletePackingList(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['packing-lists'] });
      toast.success('Packing list deleted successfully');
    },
    onError: (error: Error) =>
      toast.error(error.message || 'Failed to delete packing list'),
  });
}

export function useBulkDeletePackingLists() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (ids: string[]) => bulkDeletePackingLists(ids),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['packing-lists'] });
      toast.success(
        result?.message ?? `${result?.deleted_count ?? 0} packing list(s) deleted`,
      );
    },
    onError: (error: Error) =>
      toast.error(error.message || 'Failed to bulk delete packing lists'),
  });
}

/**
 * Checkpoint definitions for the clearance timeline.
 *
 * Configuration that changes when an admin edits it, not per-record data, so it
 * is cached hard and shared by every packing list detail page in the session.
 */
export function useClearanceCheckpoints() {
  return useQuery({
    queryKey: ['clearance-checkpoints'],
    queryFn: getClearanceCheckpoints,
    staleTime: 1000 * 60 * 30,
    retry: 1,
  });
}
