import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import { getWarehouses, getWarehouse, createWarehouse, updateWarehouse, deleteWarehouse, bulkDeleteWarehouses } from '../services/warehouseService';
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

export function useDeleteWarehouse() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteWarehouse(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['warehouses'] });
      toast.success('Warehouse deleted successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to delete warehouse'),
  });
}

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
