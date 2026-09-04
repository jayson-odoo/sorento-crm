import { useQuery } from '@tanstack/react-query';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import { getStockLedger } from '../services/stockLedgerService';
import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';

export function useStockLedger(
  params: DataGridApiFetchParams & { product_id?: string; warehouse_id?: string; transaction_type?: string },
) {
  return useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: ['stock-ledger', params.pageIndex, params.pageSize, params.sorting, params.product_id, params.warehouse_id, params.transaction_type],
    queryFn: () => getStockLedger(params),
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    retry: 1,
  });
}
