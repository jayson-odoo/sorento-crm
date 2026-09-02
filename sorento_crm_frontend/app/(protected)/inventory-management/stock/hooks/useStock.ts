import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import { getStockDashboard, getStockBalance, getStockAlerts, bulkDeleteStock } from '../services/stockService';

export function useStockDashboard() {
  return useQuery({
    queryKey: ['stock-dashboard'],
    queryFn: getStockDashboard,
    staleTime: 1000 * 60 * 5, // 5 minutes
    retry: 1,
  });
}

export function useStockBalance(params: DataGridApiFetchParams & { warehouse_id?: string; product_id?: string; category_id?: string; status?: string }) {
  return useQuery({
    queryKey: ['stock-balance', params.pageIndex, params.pageSize, params.sorting, params.searchQuery, params.warehouse_id, params.product_id, params.category_id, params.status],
    queryFn: () => getStockBalance(params),
    staleTime: 1000 * 60 * 5,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

export function useStockAlerts() {
  return useQuery({
    queryKey: ['stock-alerts'],
    queryFn: getStockAlerts,
    staleTime: 1000 * 60 * 5,
    retry: 1,
  });
}

export function useBulkDeleteStock() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (ids: string[]) => bulkDeleteStock(ids),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['stock-balance'] });
      queryClient.invalidateQueries({ queryKey: ['stock-dashboard'] });
      queryClient.invalidateQueries({ queryKey: ['stock-alerts'] });
      toast.success(result?.message ?? `${result?.deleted_count ?? 0} stock record(s) deleted`);
    },
    onError: (error: Error) =>
      toast.error(error.message || 'Failed to bulk delete stock'),
  });
}
