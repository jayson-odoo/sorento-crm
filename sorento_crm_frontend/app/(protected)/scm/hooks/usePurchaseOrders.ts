import { useMutation, useQuery, useQueryClient, type QueryKey } from '@tanstack/react-query';
import { toast } from 'sonner';
import type { SortingState } from '@tanstack/react-table';
import {
  getPurchaseOrder,
  getPurchaseOrders,
  updatePurchaseOrder,
} from '../services/purchaseOrderService';
import type { PurchaseOrderUpdateData } from '../types/scm.types';
import type { ListPagerParams, ListPagerPage } from '@/hooks/useListPager';
import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';

export interface UsePurchaseOrdersParams {
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
  /** true = something is linked to it, false = nothing is, null/undefined = every order. */
  allocated?: boolean | null;
  /** Only these order numbers - the book one upload wrote (AC-H13). */
  documents?: string[] | null;
}

/**
 * The list's React Query key. The detail page's pager rebuilds the SAME key from
 * the URL, so it reads the page the list already fetched.
 */
export function purchaseOrdersListQueryKey(
  params: UsePurchaseOrdersParams,
): QueryKey {
  return ['scm', 'purchase-orders', params];
}

/** The list query a detail URL describes, in the shape the list passes. */
export function purchaseOrdersListParamsFromUrl(
  params: ListPagerParams,
): UsePurchaseOrdersParams {
  return {
    pageIndex: params.pageIndex,
    pageSize: params.pageSize,
    sorting: params.sorting,
    searchQuery: params.searchQuery,
    status: params.filters.status || null,
    supplier: null,
    productCode: params.filters.product_code || null,
    // Three states, not two: the list's All / Outstanding / Completed toggle
    // writes `true`, `false` or nothing, and reading a missing param as `false`
    // would silently narrow the walk to the completed orders.
    outstanding: params.filters.outstanding
      ? params.filters.outstanding === 'true'
      : null,
  };
}

/** The pager's two hooks into the purchase orders list. */
export const purchaseOrdersPagerQuery = {
  listQueryKey: (params: ListPagerParams): QueryKey =>
    purchaseOrdersListQueryKey(purchaseOrdersListParamsFromUrl(params)),
  fetchPage: (params: ListPagerParams): Promise<ListPagerPage> => {
    const p = purchaseOrdersListParamsFromUrl(params);
    return getPurchaseOrders({
      pageIndex: p.pageIndex,
      pageSize: p.pageSize,
      sortField: p.sorting?.[0]?.id,
      sortDir: p.sorting?.[0]?.desc ? 'desc' : 'asc',
      searchQuery: p.searchQuery,
      status: p.status,
      supplier: p.supplier,
      productCode: p.productCode ?? null,
      outstanding: p.outstanding ?? null,
      allocated: p.allocated ?? null,
      documents: p.documents ?? null,
    });
  },
};

export function usePurchaseOrders(params: UsePurchaseOrdersParams) {
  return useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: purchaseOrdersListQueryKey(params),
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
        allocated: params.allocated ?? null,
        documents: params.documents ?? null,
      }),
    staleTime: 10_000,
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
