import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { buildDataGridParams } from '@/lib/api-client';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import {
  useRecordNeighbours,
  type RecordNeighboursResult,
} from '@/hooks/useRecordNeighbours';
import {
  ORDER_NEIGHBOURS_PATH,
  getOrders,
  getOrder,
  createOrder,
  updateOrder,
  deleteOrder,
  bulkDeleteOrders,
  createOrderLine,
  updateOrderLine,
  deleteOrderLine,
  bulkDeleteOrderLines,
} from '../services/orderService';
import type { Order, OrderFormData, OrderLineFormData } from '../types/order.types';
import { postListQuerySearch } from '@/lib/list-query/listQueryService';
import type { ListQueryFilterGroup } from '@/lib/list-query/listQueryService';

/** List query (search/sort + order filters) the neighbours pager walks within. */
export type OrderNeighboursListParams = DataGridApiFetchParams & {
  order_status_id?: string;
  has_order_lines?: 'all' | 'yes' | 'no';
};

/**
 * Prev/next neighbours of an order within the active filtered+sorted list set.
 * Serializes the list query (search/sort) with `buildDataGridParams` — the same
 * serialization the list page uses — and threads the order-specific filters
 * (order_status_id, has_order_lines) so the backend honours filters identically.
 * `page`/`limit` are sent but ignored by the neighbours endpoint.
 */
export function useOrderNeighbours(
  orderId: string | null,
  listParams: OrderNeighboursListParams,
): RecordNeighboursResult {
  const params = buildDataGridParams(listParams, {
    order_status_id:
      listParams.order_status_id && listParams.order_status_id !== 'all'
        ? listParams.order_status_id
        : undefined,
    has_order_lines:
      listParams.has_order_lines && listParams.has_order_lines !== 'all'
        ? listParams.has_order_lines
        : undefined,
  });
  return useRecordNeighbours(ORDER_NEIGHBOURS_PATH, orderId, params);
}

export function useOrders(
  params: DataGridApiFetchParams & {
    customer_id?: string;
    order_status_id?: string;
    has_order_lines?: 'all' | 'yes' | 'no';
    advancedFilter?: ListQueryFilterGroup | null;
  },
) {
  return useQuery({
    queryKey: [
      'orders',
      params.pageIndex,
      params.pageSize,
      params.sorting,
      params.searchQuery,
      params.customer_id,
      params.order_status_id,
      params.has_order_lines,
      params.advancedFilter,
    ],
    queryFn: async () => {
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
    },
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

export function useBulkDeleteOrders() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (ids: string[]) => bulkDeleteOrders(ids),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['orders'] });
      toast.success(result?.message ?? `${result?.deleted_count ?? 0} delivery order(s) deleted`);
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to bulk delete delivery orders'),
  });
}

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
