import { useQuery } from '@tanstack/react-query';
import type { SortingState } from '@tanstack/react-table';
import { getPurchaseOrders } from '../services/purchaseOrderService';

interface UsePurchaseOrdersParams {
  pageIndex: number;
  pageSize: number;
  sorting: SortingState;
  searchQuery: string;
  status: string | null;
  supplier: string | null;
}

export function usePurchaseOrders(params: UsePurchaseOrdersParams) {
  return useQuery({
    queryKey: ['scm', 'purchase-orders', params],
    queryFn: () =>
      getPurchaseOrders({
        pageIndex: params.pageIndex,
        pageSize: params.pageSize,
        sortField: params.sorting?.[0]?.id,
        sortDir: params.sorting?.[0]?.desc ? 'desc' : 'asc',
        searchQuery: params.searchQuery,
        status: params.status,
        supplier: params.supplier,
      }),
    staleTime: 10_000,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}
