import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import { getOrders, getOrder, createOrder, updateOrder, deleteOrder, bulkDeleteOrders } from '../services/orderService';
import type { OrderFormData } from '../types/order.types';

export function useOrders(params: DataGridApiFetchParams & { customer_id?: string; order_status_id?: string }) {
  return useQuery({
    queryKey: ['orders', params.pageIndex, params.pageSize, params.sorting, params.searchQuery, params.customer_id, params.order_status_id],
    queryFn: () => getOrders(params),
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
      if (!id) throw new Error('Order ID is required');
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
      toast.success('Order created successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to create order'),
  });
}

export function useUpdateOrder() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<OrderFormData> }) => updateOrder(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['orders'] });
      queryClient.invalidateQueries({ queryKey: ['order'] });
      toast.success('Order updated successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to update order'),
  });
}

export function useDeleteOrder() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteOrder(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['orders'] });
      toast.success('Order deleted successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to delete order'),
  });
}

export function useBulkDeleteOrders() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (ids: string[]) => bulkDeleteOrders(ids),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['orders'] });
      toast.success(result?.message ?? `${result?.deleted_count ?? 0} order(s) deleted`);
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to bulk delete orders'),
  });
}
