import { useQuery } from '@tanstack/react-query';
import type { SortingState } from '@tanstack/react-table';
import { getPurchaseOrder, getPurchaseOrders } from '../services/purchaseOrderService';

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

/** Single PO for the detail page. `null` data = not found (render empty state). */
export function usePurchaseOrder(id: string | null) {
  return useQuery({
    queryKey: ['scm', 'purchase-orders', 'detail', id],
    queryFn: () => getPurchaseOrder(id as string),
    enabled: !!id,
    staleTime: 5_000,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}
