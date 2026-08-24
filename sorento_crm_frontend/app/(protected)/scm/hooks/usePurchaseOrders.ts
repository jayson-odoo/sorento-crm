import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import type { SortingState } from '@tanstack/react-table';
import {
  getPurchaseOrder,
  getPurchaseOrders,
  updatePurchaseOrder,
} from '../services/purchaseOrderService';
import type { PurchaseOrderUpdateData } from '../types/scm.types';

interface UsePurchaseOrdersParams {
  pageIndex: number;
  pageSize: number;
  sorting: SortingState;
  searchQuery: string;
  status: string | null;
  supplier: string | null;
  /** Keep only orders carrying this SKU; the response then carries what we last paid. */
  productCode?: string | null;
  /** true = outstanding only, false = closed only, null/undefined = every status. */
  outstanding?: boolean | null;
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
        productCode: params.productCode ?? null,
        outstanding: params.outstanding ?? null,
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

/**
 * Correct a purchase order from its detail page. The twin of `useUpdateSalesOrder`.
 *
 * `net-position` is invalidated alongside the list because an edited quantity or a removed
 * line changes what is on order, and the planning screens read that the moment they are
 * opened next.
 */
export function useUpdatePurchaseOrder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: PurchaseOrderUpdateData }) =>
      updatePurchaseOrder(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['scm', 'purchase-orders'] });
      qc.invalidateQueries({ queryKey: ['scm', 'net-position'] });
      toast.success('Purchase order updated');
    },
    onError: (e: Error) => toast.error(e.message || 'Failed to update purchase order'),
  });
}
