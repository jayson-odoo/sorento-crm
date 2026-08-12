import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { isDeferredFormAction } from '@/app/(protected)/sla-management/_shared/formAction';
import { buildDataGridParams } from '@/lib/api-client';
import {
  useRecordNeighbours,
  type RecordNeighboursResult,
} from '@/hooks/useRecordNeighbours';
import {
  COMPLAINT_NEIGHBOURS_PATH,
  complaintListExtraParams,
  type ComplaintsListParams,
} from '../services/complaintService';
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

/**
 * Prev/next neighbours of a complaint within the active filtered+sorted list set.
 * Serializes the list query (search/sort/assignee/status) with `buildDataGridParams`
 * - the same serialization the list page uses - so the backend honours filters
 * identically. `page`/`limit` are sent but ignored by the neighbours endpoint.
 */
export function useComplaintNeighbours(
  complaintId: string | null,
  listParams: ComplaintsListParams,
): RecordNeighboursResult {
  const params = buildDataGridParams(
    listParams,
    complaintListExtraParams(listParams),
  );
  return useRecordNeighbours(COMPLAINT_NEIGHBOURS_PATH, complaintId, params);
}

export function useComplaints(params: ComplaintsListParams) {
  return useQuery({
    queryKey: [
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
    ],
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
