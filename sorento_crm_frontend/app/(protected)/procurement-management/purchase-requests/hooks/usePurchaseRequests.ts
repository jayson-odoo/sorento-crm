import { useQuery, useMutation, useQueryClient, type QueryKey } from '@tanstack/react-query';
import { toast } from 'sonner';

import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import {
  getPurchaseRequests,
  getPurchaseRequest,
  getPurchaseRequestRevisions,
  createPurchaseRequest,
  updatePurchaseRequest,
  deletePurchaseRequest,
  bulkDeletePurchaseRequests,
  updatePurchaseRequestAndReply,
  deletePurchaseRequestAttachment,
  getPurchaseRequestConversation,
  exportPurchaseRequestPdf,
} from '../services/purchaseRequestService';
import type { PurchaseRequestUpdateAndReplyData } from '../services/purchaseRequestService';
import type { PurchaseRequestFormData } from '../types/purchaseRequest.types';
import type { FormPdfExportOptions } from '@/lib/revision-export';
import { requestTypeLabel, requestTypeLabelLower } from '../lib/purchase-request-field-labels';
import type { ListPagerParams, ListPagerPage } from '@/hooks/useListPager';


export type PurchaseRequestsListQueryParams = DataGridApiFetchParams & {
  requestType?: string;
  approvalStatus?: string;
  assignedTo?: string;
};

/**
 * The list's React Query key. The detail page's pager rebuilds the SAME key from
 * the URL, so it reads the page the list already fetched.
 */
export function purchaseRequestsListQueryKey(
  params: PurchaseRequestsListQueryParams,
): QueryKey {
  return [
    'purchase-requests',
    params.pageIndex,
    params.pageSize,
    params.sorting,
    params.searchQuery,
    params.requestType,
    params.approvalStatus,
    params.assignedTo,
  ];
}

/** The list query a detail URL describes, in the shape the list passes. */
export function purchaseRequestsListParamsFromUrl(
  params: ListPagerParams,
): PurchaseRequestsListQueryParams {
  return {
    pageIndex: params.pageIndex,
    pageSize: params.pageSize,
    sorting: params.sorting,
    searchQuery: params.searchQuery,
    requestType: params.filters.request_type,
    approvalStatus: params.filters.approval_status,
    assignedTo: params.filters.assigned_to,
  };
}

/** The pager's two hooks into the purchase requests list. */
export const purchaseRequestsPagerQuery = {
  listQueryKey: (params: ListPagerParams): QueryKey =>
    purchaseRequestsListQueryKey(purchaseRequestsListParamsFromUrl(params)),
  fetchPage: (params: ListPagerParams): Promise<ListPagerPage> =>
    getPurchaseRequests(purchaseRequestsListParamsFromUrl(params)),
};

export function usePurchaseRequests(params: PurchaseRequestsListQueryParams) {
  return useQuery({
    queryKey: purchaseRequestsListQueryKey(params),
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

/**
 * Revision lineage for the office Revisions panel. Keyed on `revisionNo` so a
 * revision landing while the page is open refetches the timeline instead of
 * serving the pre-revision lineage until a manual reload.
 */
export function usePurchaseRequestRevisions(
  id: string | null,
  revisionNo?: number | null,
) {
  return useQuery({
    queryKey: ['purchase-request-revisions', id, revisionNo ?? 0],
    queryFn: () => {
      if (!id) throw new Error('Purchase request ID is required');
      return getPurchaseRequestRevisions(id);
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
 * only means "queued" - invalidate the downloads feeds so the drawer and the
 * per-entity chip pick it up.
 *
 * `mutate('pr-1')` stays the current-form export. The object form carries the
 * round-6 options: one stored revision, or the form plus its whole lineage.
 */
export type ExportPurchaseRequestPdfVariables =
  | string
  | { id: string; options?: FormPdfExportOptions | null };

export function useExportPurchaseRequestPdf() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (variables: ExportPurchaseRequestPdfVariables) =>
      typeof variables === 'string'
        ? exportPurchaseRequestPdf(variables)
        : exportPurchaseRequestPdf(variables.id, variables.options),
    onSuccess: (_, variables) => {
      const id = typeof variables === 'string' ? variables : variables.id;
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
