import { useQuery, useMutation, useQueryClient, type QueryKey } from '@tanstack/react-query';
import { toast } from '@/lib/toast';

import {
  getGRNs,
  getGRN,
  createGRN,
  updateGRN,
  deleteGRN,
  bulkDeleteGRNs,
  type GRNListParams,
} from '../services/grnService';
import type { GRNFormData } from '../types/grn.types';
import type { ListPagerParams, ListPagerPage } from '@/hooks/useListPager';
import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';

/**
 * The list's React Query key. The detail page's pager rebuilds the SAME key from
 * the URL, so it reads the page the list already fetched.
 */
export function grnListQueryKey(params: GRNListParams): QueryKey {
  return [
    'grn',
    params.pageIndex,
    params.pageSize,
    params.sorting,
    params.searchQuery,
    params.picking_status,
    params.inspection_status,
    params.spo_allocation_id,
  ];
}

/** The list query a detail URL describes, in the shape the list passes. */
export function grnListParamsFromUrl(params: ListPagerParams): GRNListParams {
  return {
    pageIndex: params.pageIndex,
    pageSize: params.pageSize,
    sorting: params.sorting,
    searchQuery: params.searchQuery,
    picking_status: params.filters.picking_status,
    inspection_status: params.filters.inspection_status,
    spo_allocation_id: params.filters.spo_allocation_id,
  };
}

/** The pager's two hooks into the GRN list. */
export const grnPagerQuery = {
  listQueryKey: (params: ListPagerParams): QueryKey =>
    grnListQueryKey(grnListParamsFromUrl(params)),
  fetchPage: (params: ListPagerParams): Promise<ListPagerPage> =>
    getGRNs(grnListParamsFromUrl(params)),
};

export function useGRNs(params: GRNListParams) {
  return useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: grnListQueryKey(params),
    queryFn: () => getGRNs(params),
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    retry: 1,
  });
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
