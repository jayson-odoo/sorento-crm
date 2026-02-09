import { useQuery } from '@tanstack/react-query';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import { getStockLedger } from '../services/stockLedgerService';

export function useStockLedger(
  params: DataGridApiFetchParams & { product_id?: string; warehouse_id?: string; transaction_type?: string },
) {
  return useQuery({
    queryKey: ['stock-ledger', params.pageIndex, params.pageSize, params.sorting, params.product_id, params.warehouse_id, params.transaction_type],
    queryFn: () => getStockLedger(params),
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}
