import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { buildDataGridParams } from '@/lib/api-client';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import {
  useRecordNeighbours,
  type RecordNeighboursResult,
} from '@/hooks/useRecordNeighbours';
import { STOCK_INQUIRY_NEIGHBOURS_PATH } from '../services/stockInquiryService';
import {
  getStockInquiries,
  getStockInquiry,
  getStockInquiryRevisions,
  createStockInquiry,
  updateStockInquiry,
  updateStockInquiryAndReply,
  deleteStockInquiry,
  bulkDeleteStockInquiries,
  linkStockInquiryAttachment,
  deleteStockInquiryAttachment,
  uploadStockInquiryResponseAttachment,
  deleteStockInquiryResponseAttachment,
  submitStockInquiryForProjectSales,
  projectSalesApproveStockInquiry,
  projectSalesRejectStockInquiry,
  purchasingRejectStockInquiry,
  reopenStockInquiry,
  getStockInquiryConversation,
  exportStockInquiryPdf,
  type ResponseAttachmentUploadResult,
} from '../services/stockInquiryService';
import type { StockInquiryFormData } from '../types/stockInquiry.types';
import type { FormPdfExportOptions } from '@/lib/revision-export';
import { isDeferredFormAction } from '@/app/(protected)/sla-management/_shared/formAction';

export type StockInquiriesListParams = DataGridApiFetchParams & {
  statuses?: string[];
};

/**
 * Prev/next neighbours of a stock inquiry within the active filtered+sorted list
 * set. Serializes the list query (search/sort/status) with `buildDataGridParams`
 * - the same serialization the list page uses - so the backend honours filters
 * identically. `page`/`limit` are sent but ignored by the neighbours endpoint.
 */
export function useStockInquiryNeighbours(
  inquiryId: string | null,
  listParams: StockInquiriesListParams,
): RecordNeighboursResult {
  const statuses = listParams.statuses?.filter(Boolean) ?? [];
  const params = buildDataGridParams(listParams, {
    status: statuses.length ? statuses.join(',') : undefined,
  });
  return useRecordNeighbours(STOCK_INQUIRY_NEIGHBOURS_PATH, inquiryId, params);
}

export function useStockInquiries(params: DataGridApiFetchParams & { statuses?: string[] }) {
  return useQuery({
    queryKey: [
      'stock-inquiries',
      params.pageIndex,
      params.pageSize,
      params.sorting,
      params.searchQuery,
      params.statuses,
    ],
    queryFn: () => getStockInquiries(params),
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

export function useStockInquiry(id: string | null) {
  return useQuery({
    queryKey: ['stock-inquiry', id],
    queryFn: () => {
      if (!id) throw new Error('Stock inquiry ID is required');
      return getStockInquiry(id);
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
export function useStockInquiryRevisions(
  id: string | null,
  revisionNo?: number | null,
) {
  return useQuery({
    queryKey: ['stock-inquiry-revisions', id, revisionNo ?? 0],
    queryFn: () => {
      if (!id) throw new Error('Stock inquiry ID is required');
      return getStockInquiryRevisions(id);
    },
    enabled: !!id,
    retry: 1,
  });
}

export function useCreateStockInquiry() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: StockInquiryFormData) => createStockInquiry(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['stock-inquiries'] });
      toast.success('Stock inquiry created successfully');
    },
    onError: (error: Error) =>
      toast.error(error.message || 'Failed to create stock inquiry'),
  });
}

export function useUpdateStockInquiry() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      data,
    }: {
      id: string;
      data: Partial<StockInquiryFormData>;
    }) => updateStockInquiry(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['stock-inquiries'] });
      queryClient.invalidateQueries({ queryKey: ['stock-inquiry'] });
      toast.success('Stock inquiry updated successfully');
    },
    onError: (error: Error) =>
      toast.error(error.message || 'Failed to update stock inquiry'),
  });
}

export function useUpdateStockInquiryAndReply() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      data,
    }: {
      id: string;
      data: Partial<StockInquiryFormData>;
    }) => updateStockInquiryAndReply(id, data),
    onSuccess: (result, { id }) => {
      workflowInvalidate(queryClient);
      queryClient.invalidateQueries({ queryKey: ['stock-inquiry-conversation', id] });
      toastActionResult(result, 'Reply sent to customer successfully');
    },
    onError: (error: Error) =>
      toast.error(error.message || 'Failed to update and reply'),
  });
}

export function useDeleteStockInquiry() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteStockInquiry(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['stock-inquiries'] });
      toast.success('Stock inquiry deleted successfully');
    },
    onError: (error: Error) =>
      toast.error(error.message || 'Failed to delete stock inquiry'),
  });
}

export function useBulkDeleteStockInquiries() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (ids: string[]) => bulkDeleteStockInquiries(ids),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['stock-inquiries'] });
      toast.success(
        result?.message ?? `${result?.deleted_count ?? 0} stock inquiry(ies) deleted`,
      );
    },
    onError: (error: Error) =>
      toast.error(error.message || 'Failed to bulk delete stock inquiries'),
  });
}

export function useLinkStockInquiryAttachment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      inquiryId,
      attachmentId,
    }: {
      inquiryId: string;
      attachmentId: string;
    }) => linkStockInquiryAttachment(inquiryId, attachmentId),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['stock-inquiry', variables.inquiryId] });
      queryClient.invalidateQueries({ queryKey: ['stock-inquiries'] });
      toast.success('Attachment linked successfully');
    },
    onError: (error: Error) =>
      toast.error(error.message || 'Failed to link attachment'),
  });
}

export function useDeleteStockInquiryAttachment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (linkId: string) => deleteStockInquiryAttachment(linkId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['stock-inquiry'] });
      queryClient.invalidateQueries({ queryKey: ['stock-inquiries'] });
      toast.success('Attachment unlinked successfully');
    },
    onError: (error: Error) =>
      toast.error(error.message || 'Failed to unlink attachment'),
  });
}

/**
 * Uploads staged response-attachment files sequentially (one request per file, per
 * the backend contract). On a partial failure, best-effort rolls back the links
 * already created in this batch so a failed submit never leaves an orphaned
 * upload - the caller's Save/Update & Reply must not proceed on error.
 */
export function useUploadStockInquiryResponseAttachments() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ inquiryId, files }: { inquiryId: string; files: File[] }) => {
      const uploaded: ResponseAttachmentUploadResult[] = [];
      try {
        for (const file of files) {
          uploaded.push(await uploadStockInquiryResponseAttachment(inquiryId, file));
        }
      } catch (err) {
        await Promise.allSettled(
          uploaded.map((u) => deleteStockInquiryResponseAttachment(u.link_id)),
        );
        throw err;
      }
      return uploaded;
    },
    onSuccess: (_data, { inquiryId }) => {
      queryClient.invalidateQueries({ queryKey: ['stock-inquiry', inquiryId] });
      queryClient.invalidateQueries({ queryKey: ['stock-inquiries'] });
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to upload attachment'),
  });
}

export function useDeleteStockInquiryResponseAttachment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (linkId: string) => deleteStockInquiryResponseAttachment(linkId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['stock-inquiry'] });
      queryClient.invalidateQueries({ queryKey: ['stock-inquiries'] });
      toast.success('Attachment unlinked successfully');
    },
    onError: (error: Error) =>
      toast.error(error.message || 'Failed to unlink attachment'),
  });
}

function workflowInvalidate(queryClient: ReturnType<typeof useQueryClient>) {
  queryClient.invalidateQueries({ queryKey: ['stock-inquiries'] });
  queryClient.invalidateQueries({ queryKey: ['stock-inquiry'] });
  // A 202 parks the action instead of moving the inquiry; the countdown banner reads
  // these two queries, so they must refetch or the deferral is invisible until reload.
  queryClient.invalidateQueries({ queryKey: ['form-action-current'] });
  queryClient.invalidateQueries({ queryKey: ['form-action-eligibility'] });
}

/** Deferred => countdown copy; immediate => the action's own success copy. */
function toastActionResult(result: unknown, immediateMessage: string) {
  if (isDeferredFormAction(result)) {
    toast.success('Action is on hold for a few seconds - you can still undo.');
  } else {
    toast.success(immediateMessage);
  }
}

export function useSubmitStockInquiryForProjectSales() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => submitStockInquiryForProjectSales(id),
    onSuccess: () => {
      workflowInvalidate(queryClient);
      toast.success('Submitted for project sales review');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to submit'),
  });
}

export function useProjectSalesApproveStockInquiry() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => projectSalesApproveStockInquiry(id),
    onSuccess: (result) => {
      workflowInvalidate(queryClient);
      toastActionResult(result, 'Approved; sent to purchasing');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to approve'),
  });
}

export function useProjectSalesRejectStockInquiry() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, reason }: { id: string; reason?: string }) =>
      projectSalesRejectStockInquiry(id, reason),
    onSuccess: (result) => {
      workflowInvalidate(queryClient);
      toastActionResult(result, 'Rejected');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to reject'),
  });
}

export function usePurchasingRejectStockInquiry() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, reason }: { id: string; reason?: string }) =>
      purchasingRejectStockInquiry(id, reason),
    onSuccess: (result) => {
      workflowInvalidate(queryClient);
      toastActionResult(result, 'Rejected');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to reject'),
  });
}

export function useReopenStockInquiry() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, reason }: { id: string; reason?: string }) =>
      reopenStockInquiry(id, reason),
    onSuccess: () => {
      workflowInvalidate(queryClient);
      toast.success('Reopened to pending project sales');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to reopen'),
  });
}

/**
 * Queue the printable Stock Inquiry Form PDF. The render happens on the worker,
 * so success only means "queued" - invalidate the downloads feeds (drawer + the
 * per-entity chip) and the list, whose Print Count column just changed.
 *
 * `mutate('si-1')` stays the current-form export. The object form carries the
 * round-6 options: one stored revision, or the form plus its whole lineage.
 */
export type ExportStockInquiryPdfVariables =
  | string
  | { id: string; options?: FormPdfExportOptions | null };

function exportPdfId(variables: ExportStockInquiryPdfVariables): string {
  return typeof variables === 'string' ? variables : variables.id;
}

export function useExportStockInquiryPdf() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (variables: ExportStockInquiryPdfVariables) =>
      typeof variables === 'string'
        ? exportStockInquiryPdf(variables)
        : exportStockInquiryPdf(variables.id, variables.options),
    onSuccess: (_, variables) => {
      const id = exportPdfId(variables);
      queryClient.invalidateQueries({ queryKey: ['my-downloads'] });
      queryClient.invalidateQueries({
        queryKey: ['entity-downloads', 'stock_inquiry', id],
      });
      queryClient.invalidateQueries({ queryKey: ['stock-inquiries'] });
      toast.success('Preparing PDF… it will appear in My Downloads.');
    },
    onError: (error: Error) =>
      toast.error(error.message || 'Failed to start PDF export'),
  });
}

export function useStockInquiryConversation(
  inquiryId: string | null,
  options?: { limit?: number; cursor?: string; enabled?: boolean },
) {
  return useQuery({
    queryKey: ['stock-inquiry-conversation', inquiryId, options?.limit, options?.cursor],
    queryFn: () =>
      getStockInquiryConversation(inquiryId!, {
        limit: options?.limit ?? 50,
        cursor: options?.cursor,
      }),
    enabled: !!inquiryId && (options?.enabled !== false),
    staleTime: 30 * 1000,
  });
}
