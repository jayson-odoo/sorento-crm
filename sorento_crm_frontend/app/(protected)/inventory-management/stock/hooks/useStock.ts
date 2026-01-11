import { useQuery } from '@tanstack/react-query';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import { getStockDashboard, getStockBalance, getStockAlerts } from '../services/stockService';

export function useStockDashboard() {
  return useQuery({
    queryKey: ['stock-dashboard'],
    queryFn: getStockDashboard,
    staleTime: 1000 * 60 * 5, // 5 minutes
    retry: 1,
  });
}

export function useStockBalance(params: DataGridApiFetchParams & { warehouse_id?: string; category_id?: string; status?: string }) {
  return useQuery({
    queryKey: ['stock-balance', params.pageIndex, params.pageSize, params.sorting, params.searchQuery, params.warehouse_id, params.category_id, params.status],
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
