import { useQuery, useMutation, useQueryClient, type QueryKey } from '@tanstack/react-query';
import { toast } from 'sonner';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import { getWarehouses, getWarehouse, createWarehouse, updateWarehouse, bulkDeleteWarehouses } from '../services/warehouseService';
import type { WarehouseFormData } from '../types/warehouse.types';
import type { ListPagerParams, ListPagerPage } from '@/hooks/useListPager';

/**
 * The list's React Query key. The detail page's pager rebuilds the SAME key from
 * the URL, so it reads the page the list already fetched.
 */
export function warehousesListQueryKey(params: DataGridApiFetchParams): QueryKey {
  return [
    'warehouses',
    params.pageIndex,
    params.pageSize,
    params.sorting,
    params.searchQuery,
  ];
}

/** The list query a detail URL describes, in the shape the list passes. */
export function warehousesListParamsFromUrl(params: ListPagerParams): DataGridApiFetchParams {
  return {
    pageIndex: params.pageIndex,
    pageSize: params.pageSize,
    sorting: params.sorting,
    searchQuery: params.searchQuery,
  };
}

/** The pager's two hooks into the warehouses list. */
export const warehousesPagerQuery = {
  listQueryKey: (params: ListPagerParams): QueryKey =>
    warehousesListQueryKey(warehousesListParamsFromUrl(params)),
  fetchPage: (params: ListPagerParams): Promise<ListPagerPage> =>
    getWarehouses(warehousesListParamsFromUrl(params)),
};

export function useWarehouses(params: DataGridApiFetchParams) {
  return useQuery({
    queryKey: warehousesListQueryKey(params),
    queryFn: () => getWarehouses(params),
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

export function useWarehouse(id: string | null) {
  return useQuery({
    queryKey: ['warehouse', id],
    queryFn: () => {
      if (!id) throw new Error('Warehouse ID is required');
      return getWarehouse(id);
    },
    enabled: !!id,
    retry: 1,
  });
}

export function useCreateWarehouse() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: WarehouseFormData) => createWarehouse(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['warehouses'] });
      toast.success('Warehouse created successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to create warehouse'),
  });
}

export function useUpdateWarehouse() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<WarehouseFormData> }) => updateWarehouse(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['warehouses'] });
      queryClient.invalidateQueries({ queryKey: ['warehouse'] });
      toast.success('Warehouse updated successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to update warehouse'),
  });
}

// There is deliberately no `useDeleteWarehouse`. Single delete is a deferred record
// action since S6b: the record page parks `warehouse.delete` and the countdown, the
// toast and the invalidation all belong to `useDeferredAction`. A hook that toasted
// as well would report every outcome twice, in two positions, and a 409 ("Warehouse
// has linked stock") would say the same thing to the user twice.
// Bulk delete keeps its hook because `WarehouseBulkDeleteDialog` is a plain `Dialog`
// that owns no mutation of its own, so there is nothing for this one to double up with.

export function useBulkDeleteWarehouses() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (ids: string[]) => bulkDeleteWarehouses(ids),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['warehouses'] });
      if (result.failed?.length) {
        toast.warning(
          `Deleted ${result.deleted_count}; ${result.failed.length} failed (likely have linked stock/zones).`,
        );
      } else {
        toast.success(`Deleted ${result.deleted_count} warehouse${result.deleted_count === 1 ? '' : 's'}`);
      }
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to bulk delete warehouses'),
  });
}
