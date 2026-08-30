import { useQuery, useMutation, useQueryClient, type QueryKey } from '@tanstack/react-query';
import { toast } from 'sonner';

import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';
import {
  getOrders,
  getOrder,
  createOrder,
  updateOrder,
  deleteOrder,
  createOrderLine,
  updateOrderLine,
  deleteOrderLine,
  bulkDeleteOrderLines,
} from '../services/orderService';
import type { Order, OrderFormData, OrderLineFormData } from '../types/order.types';
import { postListQuerySearch } from '@/lib/list-query/listQueryService';
import type { ListQueryFilterGroup } from '@/lib/list-query/listQueryService';
import { decodeAdvancedFilter } from '@/lib/listNavQuery';
import type { ListPagerParams, ListPagerPage } from '@/hooks/useListPager';

/** Everything the orders list filters by. */
export type OrdersListParams = DataGridApiFetchParams & {
  customer_id?: string;
  order_status_id?: string;
  has_order_lines?: 'all' | 'yes' | 'no';
  advancedFilter?: ListQueryFilterGroup | null;
};

/**
 * The list's React Query key. The detail page's pager builds the SAME key from
 * the URL, so it reads the page the list already fetched instead of asking again
 * (see `hooks/useListPager.ts`).
 */
export function ordersListQueryKey(params: OrdersListParams): QueryKey {
  return [
    'orders',
    params.pageIndex,
    params.pageSize,
    params.sorting,
    params.searchQuery,
    params.customer_id,
    params.order_status_id,
    params.has_order_lines,
    params.advancedFilter,
  ];
}

/** One page of the orders list, quick filters and advanced filter included. */
export function fetchOrdersPage(
  params: OrdersListParams,
): Promise<DataGridApiResponse<Order>> {
  if (params.advancedFilter) {
    const sortField = params.sorting?.[0]?.id || '';
    const sortDirection = params.sorting?.[0]?.desc ? 'desc' : 'asc';
    return postListQuerySearch<Order>({
      resource: 'orders',
      filter: params.advancedFilter,
      page: params.pageIndex + 1,
      limit: params.pageSize,
      sort: sortField || 'created_at',
      dir: sortDirection,
      quick_search: params.searchQuery || undefined,
      order_status_id:
        params.order_status_id && params.order_status_id !== 'all'
          ? params.order_status_id
          : undefined,
      has_order_lines:
        params.has_order_lines && params.has_order_lines !== 'all'
          ? params.has_order_lines
          : undefined,
      customer_id: params.customer_id,
    });
  }
  return getOrders(params);
}

/**
 * The list query a detail URL describes, in the exact shape `OrdersList` passes
 * to `useOrders` - equal values, so the keys hash equal.
 */
export function ordersListParamsFromUrl(params: ListPagerParams): OrdersListParams {
  const lines = params.filters.has_order_lines;
  return {
    pageIndex: params.pageIndex,
    pageSize: params.pageSize,
    sorting: params.sorting,
    searchQuery: params.searchQuery,
    order_status_id: params.filters.order_status_id,
    has_order_lines: lines === 'yes' || lines === 'no' ? lines : 'all',
    advancedFilter:
      decodeAdvancedFilter<ListQueryFilterGroup>(params.filters.advFilter) ?? undefined,
  };
}

/** The pager's two hooks into the orders list, ready to spread into `ListPager`. */
export const ordersPagerQuery = {
  listQueryKey: (params: ListPagerParams): QueryKey =>
    ordersListQueryKey(ordersListParamsFromUrl(params)),
  fetchPage: (params: ListPagerParams): Promise<ListPagerPage> =>
    fetchOrdersPage(ordersListParamsFromUrl(params)),
};

export function useOrders(params: OrdersListParams) {
  return useQuery({
    queryKey: ordersListQueryKey(params),
    queryFn: () => fetchOrdersPage(params),
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

export function useOrder(id: string | null) {
  return useQuery({
    queryKey: ['order', id],
    queryFn: () => {
      if (!id) throw new Error('Delivery order ID is required');
      return getOrder(id);
    },
    enabled: !!id,
    retry: 1,
  });
}

export function useCreateOrder() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: OrderFormData) => createOrder(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['orders'] });
      toast.success('Delivery order created successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to create delivery order'),
  });
}

export function useUpdateOrder() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<OrderFormData> }) => updateOrder(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['orders'] });
      queryClient.invalidateQueries({ queryKey: ['order'] });
      toast.success('Delivery order updated successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to update delivery order'),
  });
}

export function useDeleteOrder() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteOrder(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['orders'] });
      toast.success('Delivery order deleted successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to delete delivery order'),
  });
}

// Bulk delete has no mutation hook: the list parks one `order.delete` per selected row
// behind one countdown (`useDeferredBulkAction`, D7).

export function useCreateOrderLine() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ orderId, data }: { orderId: string; data: OrderLineFormData }) => createOrderLine(orderId, data),
    onSuccess: (_, { orderId }) => {
      queryClient.invalidateQueries({ queryKey: ['orders'] });
      queryClient.invalidateQueries({ queryKey: ['order', orderId] });
      toast.success('Delivery order line added');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to add delivery order line'),
  });
}

export function useUpdateOrderLine() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ orderId, lineId, data }: { orderId: string; lineId: string; data: Partial<OrderLineFormData> }) =>
      updateOrderLine(orderId, lineId, data),
    onSuccess: (_, { orderId }) => {
      queryClient.invalidateQueries({ queryKey: ['orders'] });
      queryClient.invalidateQueries({ queryKey: ['order', orderId] });
      toast.success('Delivery order line updated');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to update delivery order line'),
  });
}

export function useDeleteOrderLine() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ orderId, lineId }: { orderId: string; lineId: string }) => deleteOrderLine(orderId, lineId),
    onSuccess: (_, { orderId }) => {
      queryClient.invalidateQueries({ queryKey: ['orders'] });
      queryClient.invalidateQueries({ queryKey: ['order', orderId] });
      toast.success('Delivery order line removed');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to remove delivery order line'),
  });
}

export function useBulkDeleteOrderLines() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ orderId, ids }: { orderId: string; ids: string[] }) =>
      bulkDeleteOrderLines(orderId, ids),
    onSuccess: (result, { orderId }) => {
      queryClient.invalidateQueries({ queryKey: ['orders'] });
      queryClient.invalidateQueries({ queryKey: ['order', orderId] });
      toast.success(
        result?.message ?? `${result?.deleted_count ?? 0} delivery order line(s) deleted`,
      );
    },
    onError: (error: Error) =>
      toast.error(error.message || 'Failed to bulk delete delivery order lines'),
  });
}
