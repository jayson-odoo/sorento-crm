import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import {
  getPurchaseRequests,
  getPurchaseRequest,
  createPurchaseRequest,
  updatePurchaseRequest,
  deletePurchaseRequest,
  bulkDeletePurchaseRequests,
  updatePurchaseRequestAndReply,
  deletePurchaseRequestAttachment,
  getPurchaseRequestConversation,
} from '../services/purchaseRequestService';
import type { PurchaseRequestUpdateAndReplyData } from '../services/purchaseRequestService';
import type { PurchaseRequestFormData } from '../types/purchaseRequest.types';

export function usePurchaseRequests(
  params: DataGridApiFetchParams & {
    requestType?: string;
    approvalStatus?: string;
    assignedTo?: string;
  },
) {
  return useQuery({
    queryKey: [
      'purchase-requests',
      params.pageIndex,
      params.pageSize,
      params.sorting,
      params.searchQuery,
      params.requestType,
      params.approvalStatus,
      params.assignedTo,
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

export function useBulkDeletePurchaseRequests() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (ids: string[]) => bulkDeletePurchaseRequests(ids),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['purchase-requests'] });
      toast.success(
        data.deleted_count === 1
          ? '1 record deleted successfully'
          : `${data.deleted_count} records deleted successfully`,
      );
    },
    onError: (error: Error) =>
      toast.error(error.message || 'Failed to bulk delete'),
  });
}

export function useUpdatePurchaseRequestAndReply() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      data,
    }: {
      id: string;
      data: PurchaseRequestUpdateAndReplyData;
    }) => updatePurchaseRequestAndReply(id, data),
    onSuccess: (_, { id }) => {
      queryClient.invalidateQueries({ queryKey: ['purchase-requests'] });
      queryClient.invalidateQueries({ queryKey: ['purchase-request', id] });
      queryClient.invalidateQueries({ queryKey: ['purchase-request-conversation', id] });
      toast.success('Updated and reply sent to conversation');
    },
    onError: (error: Error) =>
      toast.error(error.message || 'Failed to update and reply'),
  });
}

export function useDeletePurchaseRequestAttachment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (linkId: string) => deletePurchaseRequestAttachment(linkId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['purchase-requests'] });
      queryClient.invalidateQueries({ queryKey: ['purchase-request'] });
      toast.success('Attachment unlinked');
    },
    onError: (error: Error) =>
      toast.error(error.message || 'Failed to unlink attachment'),
  });
}

export function usePurchaseRequestConversation(
  requestId: string | null,
  options?: { limit?: number; cursor?: string; enabled?: boolean },
) {
  return useQuery({
    queryKey: ['purchase-request-conversation', requestId, options?.limit, options?.cursor],
    queryFn: () =>
      getPurchaseRequestConversation(requestId!, {
        limit: options?.limit ?? 50,
        cursor: options?.cursor,
      }),
    enabled: !!requestId && (options?.enabled !== false),
    staleTime: 30 * 1000,
  });
}
