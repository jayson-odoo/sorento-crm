import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import { getOrderStatuses, getOrderStatus, createOrderStatus, updateOrderStatus, deleteOrderStatus } from '../services/orderStatusService';
import type { OrderStatusFormData } from '../types/orderStatus.types';

export function useOrderStatuses(params: DataGridApiFetchParams) {
  return useQuery({
    queryKey: ['order-statuses', params.pageIndex, params.pageSize, params.sorting, params.searchQuery],
    queryFn: () => getOrderStatuses(params),
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

export function useOrderStatus(id: string | null) {
  return useQuery({
    queryKey: ['order-status', id],
    queryFn: () => {
      if (!id) throw new Error('Delivery order status ID is required');
      return getOrderStatus(id);
    },
    enabled: !!id,
    retry: 1,
  });
}

export function useCreateOrderStatus() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: OrderStatusFormData) => createOrderStatus(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['order-statuses'] });
      toast.success('Delivery order status created successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to create delivery order status'),
  });
}

export function useUpdateOrderStatus() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<OrderStatusFormData> }) => updateOrderStatus(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['order-statuses'] });
      queryClient.invalidateQueries({ queryKey: ['order-status'] });
      toast.success('Delivery order status updated successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to update delivery order status'),
  });
}

export function useDeleteOrderStatus() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteOrderStatus(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['order-statuses'] });
      toast.success('Delivery order status deleted successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to delete delivery order status'),
  });
}
