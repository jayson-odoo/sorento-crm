import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import { getWarehouses, getWarehouse, createWarehouse, updateWarehouse, bulkDeleteWarehouses } from '../services/warehouseService';
import type { WarehouseFormData } from '../types/warehouse.types';

export function useWarehouses(params: DataGridApiFetchParams) {
  return useQuery({
    queryKey: ['warehouses', params.pageIndex, params.pageSize, params.sorting, params.searchQuery],
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

// There is deliberately no `useDeleteWarehouse`. Single delete goes through the shared
// `ConfirmDeleteDialog`, which wraps the `onDelete` callback in its OWN mutation and owns the
// toast plus the query invalidation. A hook that also toasted and invalidated meant every delete
// reported itself twice, in two positions, and a 409 ("Warehouse has linked stock") said the same
// thing to the user twice. Pass the bare `deleteWarehouse` service call to the dialog instead.
// Bulk delete keeps its hook because `WarehouseBulkDeleteDialog` is a plain `Dialog` that owns no
// mutation of its own, so there is nothing for this one to double up with.

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
