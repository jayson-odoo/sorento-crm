import { useQuery, useMutation, useQueryClient, type QueryKey } from '@tanstack/react-query';
import { toast } from 'sonner';
import { isDeferredFormAction } from '@/app/(protected)/sla-management/_shared/formAction';

import { type ComplaintsListParams } from '../services/complaintService';
import {
  getComplaints,
  getComplaint,
  getComplaintConversation,
  createComplaint,
  updateComplaint,
  updateComplaintAndReply,
  approveComplaint,
  rejectComplaint,
  processComplaintByCs,
  closeComplaint,
  exportComplaintPdf,
  notifyComplaintRootCause,
  notifyComplaintResolution,
  deleteComplaint,
  bulkDeleteComplaints,
  linkComplaintAttachment,
  deleteComplaintAttachment,
  uploadComplaintResponseAttachment,
  deleteComplaintResponseAttachment,
  syncComplaintAssigneeFromRespond,
  type ResponseAttachmentUploadResult,
} from '../services/complaintService';
import type { ComplaintFormData } from '../types/complaint.types';
import type { ListPagerParams, ListPagerPage } from '@/hooks/useListPager';


/**
 * The list's React Query key. The detail page's pager rebuilds the SAME key from
 * the URL, so it reads the page the list already fetched (see `hooks/useListPager.ts`).
 */
export function complaintsListQueryKey(params: ComplaintsListParams): QueryKey {
  return [
    'complaints',
    params.pageIndex,
    params.pageSize,
    params.sorting,
    params.searchQuery,
    params.assigned_to,
    params.status,
    // Join, not the array: a fresh array literal each render would be a new key.
    params.root_cause_ids?.join(',') ?? '',
    params.resolution_ids?.join(',') ?? '',
  ];
}

/** The list query a detail URL describes, in the shape the list passes. */
export function complaintsListParamsFromUrl(
  params: ListPagerParams,
): ComplaintsListParams {
  const rootCauses = params.filters.root_cause_ids;
  const resolutions = params.filters.resolution_ids;
  return {
    pageIndex: params.pageIndex,
    pageSize: params.pageSize,
    sorting: params.sorting,
    searchQuery: params.searchQuery,
    assigned_to: params.filters.assigned_to,
    status: params.filters.status,
    root_cause_ids: rootCauses ? rootCauses.split(',') : undefined,
    resolution_ids: resolutions ? resolutions.split(',') : undefined,
  };
}

/** The pager's two hooks into the complaints list. */
export const complaintsPagerQuery = {
  listQueryKey: (params: ListPagerParams): QueryKey =>
    complaintsListQueryKey(complaintsListParamsFromUrl(params)),
  fetchPage: (params: ListPagerParams): Promise<ListPagerPage> =>
    getComplaints(complaintsListParamsFromUrl(params)),
};

export function useComplaints(params: ComplaintsListParams) {
  return useQuery({
    queryKey: complaintsListQueryKey(params),
    queryFn: () => getComplaints(params),
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

export function useComplaint(id: string | null) {
  return useQuery({
    queryKey: ['complaint', id],
    queryFn: () => {
      if (!id) throw new Error('Complaint ID is required');
      return getComplaint(id);
    },
    enabled: !!id,
    retry: 1,
  });
}

export function useCreateComplaint() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: ComplaintFormData) => createComplaint(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['complaints'] });
      toast.success('Complaint created successfully');
    },
    onError: (error: Error) =>
      toast.error(error.message || 'Failed to create complaint'),
  });
}

export function useUpdateComplaint() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      data,
    }: {
      id: string;
      data: Partial<ComplaintFormData>;
    }) => updateComplaint(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['complaints'] });
      queryClient.invalidateQueries({ queryKey: ['complaint'] });
      toast.success('Complaint updated successfully');
    },
    onError: (error: Error) =>
      toast.error(error.message || 'Failed to update complaint'),
  });
}

export function useUpdateComplaintAndReply() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      data,
    }: {
      id: string;
      data: Partial<ComplaintFormData>;
    }) => updateComplaintAndReply(id, data),
    onSuccess: (_, { id }) => {
      queryClient.invalidateQueries({ queryKey: ['complaints'] });
      queryClient.invalidateQueries({ queryKey: ['complaint'] });
      queryClient.invalidateQueries({ queryKey: ['complaint-conversation', id] });
      toast.success('Reply sent to customer successfully');
    },
    onError: (error: Error) =>
      toast.error(error.message || 'Failed to update and reply'),
  });
}

/** Refetch everything a decision touches, including the countdown banner's reads. */
function decisionInvalidate(
  queryClient: ReturnType<typeof useQueryClient>,
  id: string,
) {
  queryClient.invalidateQueries({ queryKey: ['complaints'] });
  queryClient.invalidateQueries({ queryKey: ['complaint'] });
  queryClient.invalidateQueries({ queryKey: ['complaint-conversation', id] });
  // A 202 parks the action instead of moving the complaint; the countdown banner
  // reads these, so they must refetch or the deferral is invisible until reload.
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

export function useApproveComplaint() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => approveComplaint(id),
    onSuccess: (result, id) => {
      decisionInvalidate(queryClient, id);
      toastActionResult(result, 'Complaint approved and customer notified.');
    },
    onError: (error: Error) =>
      toast.error(error.message || 'Failed to approve complaint'),
  });
}

export function useRejectComplaint() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, rejection_reason }: { id: string; rejection_reason: string }) =>
      rejectComplaint(id, rejection_reason),
    onSuccess: (result, { id }) => {
      decisionInvalidate(queryClient, id);
      toastActionResult(result, 'Complaint rejected and customer notified.');
    },
    onError: (error: Error) =>
      toast.error(error.message || 'Failed to reject complaint'),
  });
}

export function useProcessComplaintByCs() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, note }: { id: string; note?: string }) =>
      processComplaintByCs(id, note),
    onSuccess: (result, { id }) => {
      decisionInvalidate(queryClient, id);
      toastActionResult(result, 'Complaint marked as processed by CS.');
    },
    onError: (error: Error) =>
      toast.error(error.message || 'Failed to mark complaint processed by CS'),
  });
}

export function useCloseComplaint() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, note }: { id: string; note?: string }) =>
      closeComplaint(id, note),
    onSuccess: (result, { id }) => {
      decisionInvalidate(queryClient, id);
      toastActionResult(result, 'Complaint marked as closed.');
    },
    onError: (error: Error) =>
      toast.error(error.message || 'Failed to close complaint'),
  });
}

export function useExportComplaintPdf() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => exportComplaintPdf(id),
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: ['my-downloads'] });
      queryClient.invalidateQueries({ queryKey: ['entity-downloads', 'complaint', id] });
      queryClient.invalidateQueries({ queryKey: ['complaints'] });
      toast.success('Preparing PDF… it will appear in My Downloads.');
    },
    onError: (error: Error) =>
      toast.error(error.message || 'Failed to start PDF export'),
  });
}

export function useNotifyComplaintRootCause() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => notifyComplaintRootCause(id),
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: ['complaints'] });
      queryClient.invalidateQueries({ queryKey: ['complaint'] });
      queryClient.invalidateQueries({ queryKey: ['complaint-conversation', id] });
      toast.success('Salesperson notified.');
    },
    onError: (error: Error) =>
      toast.error(error.message || 'Failed to notify salesperson on root cause'),
  });
}

export function useNotifyComplaintResolution() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => notifyComplaintResolution(id),
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: ['complaints'] });
      queryClient.invalidateQueries({ queryKey: ['complaint'] });
      queryClient.invalidateQueries({ queryKey: ['complaint-conversation', id] });
      toast.success('Salesperson notified.');
    },
    onError: (error: Error) =>
      toast.error(error.message || 'Failed to notify salesperson on resolution'),
  });
}

export function useComplaintConversation(
  complaintId: string | null,
  options?: { limit?: number; cursor?: string; enabled?: boolean },
) {
  return useQuery({
    queryKey: ['complaint-conversation', complaintId, options?.limit, options?.cursor],
    queryFn: () =>
      getComplaintConversation(complaintId!, {
        limit: options?.limit ?? 50,
        cursor: options?.cursor,
      }),
    enabled: !!complaintId && (options?.enabled !== false),
    staleTime: 30 * 1000,
  });
}

export function useDeleteComplaint() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteComplaint(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['complaints'] });
      toast.success('Complaint deleted successfully');
    },
    onError: (error: Error) =>
      toast.error(error.message || 'Failed to delete complaint'),
  });
}

export function useBulkDeleteComplaints() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (ids: string[]) => bulkDeleteComplaints(ids),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['complaints'] });
      queryClient.invalidateQueries({ queryKey: ['complaint'] });
      toast.success(data?.message ?? 'Complaints deleted successfully');
    },
    onError: (error: Error) =>
      toast.error(error.message || 'Failed to bulk delete complaints'),
  });
}

export function useLinkComplaintAttachment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      complaintId,
      attachmentId,
    }: {
      complaintId: string;
      attachmentId: string;
    }) => linkComplaintAttachment(complaintId, attachmentId),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['complaint', variables.complaintId] });
      queryClient.invalidateQueries({ queryKey: ['complaints'] });
      toast.success('Attachment linked successfully');
    },
    onError: (error: Error) =>
      toast.error(error.message || 'Failed to link attachment'),
  });
}

export function useDeleteComplaintAttachment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (linkId: string) => deleteComplaintAttachment(linkId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['complaint'] });
      queryClient.invalidateQueries({ queryKey: ['complaints'] });
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
export function useUploadComplaintResponseAttachments() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ complaintId, files }: { complaintId: string; files: File[] }) => {
      const uploaded: ResponseAttachmentUploadResult[] = [];
      try {
        for (const file of files) {
          uploaded.push(await uploadComplaintResponseAttachment(complaintId, file));
        }
      } catch (err) {
        await Promise.allSettled(
          uploaded.map((u) => deleteComplaintResponseAttachment(u.link_id)),
        );
        throw err;
      }
      return uploaded;
    },
    onSuccess: (_data, { complaintId }) => {
      queryClient.invalidateQueries({ queryKey: ['complaint', complaintId] });
      queryClient.invalidateQueries({ queryKey: ['complaints'] });
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to upload attachment'),
  });
}

export function useDeleteComplaintResponseAttachment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (linkId: string) => deleteComplaintResponseAttachment(linkId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['complaint'] });
      queryClient.invalidateQueries({ queryKey: ['complaints'] });
      toast.success('Attachment unlinked successfully');
    },
    onError: (error: Error) =>
      toast.error(error.message || 'Failed to unlink attachment'),
  });
}

export function useComplaintSyncAssignee() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (complaintId: string) => syncComplaintAssigneeFromRespond(complaintId),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['complaint'] });
      queryClient.invalidateQueries({ queryKey: ['complaints'] });
      const message = data?.message ?? (data?.updated ? 'Assignee synced from Respond.io.' : 'Sync successful.');
      toast.success(message);
    },
    onError: (error: Error) =>
      toast.error(error.message || 'Failed to sync assignee from Respond.io.'),
  });
}
