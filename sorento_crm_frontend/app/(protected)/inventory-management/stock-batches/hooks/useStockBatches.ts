import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import { getStockBatches, getStockBatch, createStockBatch, updateStockBatch, deleteStockBatch, bulkAddSerialNumbers } from '../services/batchService';
import type { BatchFormData } from '../types/batch.types';
import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';

export function useStockBatches(params: DataGridApiFetchParams & { warehouse_id?: string; product_id?: string; status?: string }) {
  return useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: ['stock-batches', params.pageIndex, params.pageSize, params.sorting, params.searchQuery, params.warehouse_id, params.product_id, params.status],
    queryFn: () => getStockBatches(params),
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    retry: 1,
  });
}

export function useStockBatch(id: string | null) {
  return useQuery({
    queryKey: ['stock-batch', id],
    queryFn: () => {
      if (!id) throw new Error('Stock batch ID is required');
      return getStockBatch(id);
    },
    enabled: !!id,
    retry: 1,
  });
}

export function useCreateStockBatch() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: BatchFormData) => createStockBatch(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['stock-batches'] });
      toast.success('Stock batch created successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to create stock batch'),
  });
}

export function useUpdateStockBatch() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<BatchFormData> }) => updateStockBatch(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['stock-batches'] });
      queryClient.invalidateQueries({ queryKey: ['stock-batch'] });
      toast.success('Stock batch updated successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to update stock batch'),
  });
}

export function useDeleteStockBatch() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteStockBatch(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['stock-batches'] });
      toast.success('Stock batch deleted successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to delete stock batch'),
  });
}

export function useBulkAddSerialNumbers() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ batchId, serialNumbers }: { batchId: string; serialNumbers: string[] }) =>
      bulkAddSerialNumbers(batchId, serialNumbers),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['stock-batch', variables.batchId] });
      toast.success('Serial numbers added successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to add serial numbers'),
  });
}
