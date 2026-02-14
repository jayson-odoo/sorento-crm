import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import {
  getPurchaseRequests,
  getPurchaseRequest,
  getPurchaseRequestNeighbours,
  createPurchaseRequest,
  updatePurchaseRequest,
  deletePurchaseRequest,
} from '../services/purchaseRequestService';
import type { PurchaseRequestFormData } from '../types/purchaseRequest.types';

export function usePurchaseRequests(
  params: DataGridApiFetchParams & { requestType?: string },
) {
  return useQuery({
    queryKey: [
      'purchase-requests',
      params.pageIndex,
      params.pageSize,
      params.sorting,
      params.searchQuery,
      params.requestType,
    ],
    queryFn: () => getPurchaseRequests(params),
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

export function usePurchaseRequest(id: string | null) {
  return useQuery({
    queryKey: ['purchase-request', id],
    queryFn: () => {
      if (!id) throw new Error('Purchase request ID is required');
      return getPurchaseRequest(id);
    },
    enabled: !!id,
    retry: 1,
  });
}

export function usePurchaseRequestNeighbours(
  requestId: string | null,
  requestType?: string | null,
) {
  return useQuery({
    queryKey: ['purchase-request-neighbours', requestId, requestType],
    queryFn: () => {
      if (!requestId) return { prev_id: null, next_id: null };
      return getPurchaseRequestNeighbours(requestId, requestType);
    },
    enabled: !!requestId,
    staleTime: 60 * 1000,
  });
}

export function useCreatePurchaseRequest() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: PurchaseRequestFormData) => createPurchaseRequest(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['purchase-requests'] });
      toast.success('Purchase request created successfully');
    },
    onError: (error: Error) =>
      toast.error(error.message || 'Failed to create purchase request'),
  });
}

export function useUpdatePurchaseRequest() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      data,
    }: {
      id: string;
      data: Partial<PurchaseRequestFormData>;
    }) => updatePurchaseRequest(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['purchase-requests'] });
      queryClient.invalidateQueries({ queryKey: ['purchase-request'] });
      toast.success('Purchase request updated successfully');
    },
    onError: (error: Error) =>
      toast.error(error.message || 'Failed to update purchase request'),
  });
}

export function useDeletePurchaseRequest() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deletePurchaseRequest(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['purchase-requests'] });
      toast.success('Purchase request deleted successfully');
    },
    onError: (error: Error) =>
      toast.error(error.message || 'Failed to delete purchase request'),
  });
}
