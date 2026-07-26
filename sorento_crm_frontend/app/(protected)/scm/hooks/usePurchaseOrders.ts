import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import type { SortingState } from '@tanstack/react-table';
import {
  annotatePurchaseOrder,
  getPurchaseOrder,
  getPurchaseOrders,
} from '../services/purchaseOrderService';
import type { MirrorAnnotationPayload } from '../types/scm.types';

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

/**
 * Annotate a purchase order (internal note + follow-up) — the only mutation
 * allowed on an AutoCount-mirrored PO. Invalidates the list + the PO's detail
 * query so the saved note reflects immediately.
 */
export function useAnnotatePurchaseOrder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: MirrorAnnotationPayload }) =>
      annotatePurchaseOrder(id, data),
    onSuccess: (_res, { id }) => {
      qc.invalidateQueries({ queryKey: ['scm', 'purchase-orders'] });
      qc.invalidateQueries({ queryKey: ['scm', 'purchase-orders', 'detail', id] });
      toast.success('Note saved');
    },
    onError: (e: Error) => toast.error(e.message || 'Failed to save note'),
  });
}
