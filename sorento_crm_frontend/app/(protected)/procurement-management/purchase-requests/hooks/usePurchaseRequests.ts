import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { buildDataGridParams } from '@/lib/api-client';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import {
  useRecordNeighbours,
  type RecordNeighboursResult,
} from '@/hooks/useRecordNeighbours';
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
  PURCHASE_REQUEST_NEIGHBOURS_PATH,
  exportPurchaseRequestPdf,
} from '../services/purchaseRequestService';
import type {
  PurchaseRequestUpdateAndReplyData,
  PurchaseRequestsListParams,
} from '../services/purchaseRequestService';
import type { PurchaseRequestFormData } from '../types/purchaseRequest.types';
import { requestTypeLabel, requestTypeLabelLower } from '../lib/purchase-request-field-labels';

/**
 * Prev/next neighbours of a purchase request / sponsorship form within the active
 * filtered+sorted list set. Serializes the list query (search/sort/request_type/
 * approval_status/assigned_to) with `buildDataGridParams` — the same serialization
 * the list page uses — so the backend honours filters identically. `request_type`
 * is forwarded so PR navigation stays within PRs and SF within SFs. `page`/`limit`
 * are sent but ignored by the neighbours endpoint.
 */
export function usePurchaseRequestNeighbours(
  requestId: string | null,
  listParams: PurchaseRequestsListParams,
): RecordNeighboursResult {
  const params = buildDataGridParams(listParams, {
    request_type: listParams.request_type,
    approval_status: listParams.approval_status,
    assigned_to: listParams.assigned_to,
  });
  return useRecordNeighbours(
    PURCHASE_REQUEST_NEIGHBOURS_PATH,
    requestId,
    params,
  );
}

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
    onSuccess: (_, data) => {
      queryClient.invalidateQueries({ queryKey: ['purchase-requests'] });
      toast.success(`${requestTypeLabel(data?.request_type)} created successfully`);
    },
    onError: (error: Error, data) =>
      toast.error(error.message || `Failed to create ${requestTypeLabelLower(data?.request_type)}`),
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
    onSuccess: (_, { data }) => {
      queryClient.invalidateQueries({ queryKey: ['purchase-requests'] });
      queryClient.invalidateQueries({ queryKey: ['purchase-request'] });
      toast.success(`${requestTypeLabel(data?.request_type)} updated successfully`);
    },
    onError: (error: Error, { data }) =>
      toast.error(error.message || `Failed to update ${requestTypeLabelLower(data?.request_type)}`),
  });
}

export function useDeletePurchaseRequest() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id }: { id: string; requestType?: string }) => deletePurchaseRequest(id),
    onSuccess: (_, { requestType }) => {
      queryClient.invalidateQueries({ queryKey: ['purchase-requests'] });
      toast.success(`${requestTypeLabel(requestType)} deleted successfully`);
    },
    onError: (error: Error, { requestType }) =>
      toast.error(error.message || `Failed to delete ${requestTypeLabelLower(requestType)}`),
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

/**
 * Queue a printable PR / SF PDF. Rendering is async on the RQ worker, so success
 * only means "queued" — invalidate the downloads feeds so the drawer and the
 * per-entity chip pick it up.
 */
export function useExportPurchaseRequestPdf() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => exportPurchaseRequestPdf(id),
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: ['my-downloads'] });
      queryClient.invalidateQueries({
        queryKey: ['entity-downloads', 'purchase_request', id],
      });
      toast.success('Preparing PDF… it will appear in My Downloads.');
    },
    onError: (error: Error) =>
      toast.error(error.message || 'Failed to start PDF export'),
  });
}
