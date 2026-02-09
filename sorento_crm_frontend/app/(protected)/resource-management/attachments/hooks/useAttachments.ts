import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import { getAttachments, uploadAttachment, deleteAttachment, bulkDeleteAttachments, restoreAttachment, downloadAttachment, getAttachmentMetadata, checkDuplicateByHash, resubmitAttachmentWebhook } from '../services/attachmentService';
import { apiFetch } from '@/lib/api';
import type { AttachmentType } from '../../attachment-types/types/attachmentType.types';

export function useAttachments(params: DataGridApiFetchParams & { entity_type?: string; file_type?: string; upload_date_from?: string; upload_date_to?: string; is_deleted?: boolean; virus_status?: string }) {
  return useQuery({
    queryKey: ['attachments', params.pageIndex, params.pageSize, params.sorting, params.searchQuery, params.entity_type, params.file_type, params.upload_date_from, params.upload_date_to, params.is_deleted, params.virus_status],
    queryFn: () => getAttachments(params),
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

export function useUploadAttachment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ file, attachmentTypeId, entityType, entityId, accessLevels }: { file: File; attachmentTypeId: string; entityType?: string; entityId?: string; accessLevels?: string[] }) =>
      uploadAttachment(file, attachmentTypeId, entityType, entityId, accessLevels),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['attachments'] });
      // Toast will be shown by the dialog component for multiple files
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to upload file'),
  });
}

export function useAttachmentTypesList() {
  return useQuery({
    queryKey: ['attachment-types-list'],
    queryFn: async () => {
      const response = await apiFetch('/api/v1/resource-management/attachment-types');
      if (!response.ok) throw new Error('Failed to fetch attachment types');
      const data = await response.json();
      return (data.data || []) as AttachmentType[];
    },
    staleTime: 1000 * 60 * 5, // 5 minutes
    gcTime: 1000 * 60 * 60,
  });
}

export function useDeleteAttachment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteAttachment(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['attachments'] });
      toast.success('Attachment deleted successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to delete attachment'),
  });
}

export function useBulkDeleteAttachments() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (ids: string[]) => bulkDeleteAttachments(ids),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['attachments'] });
      const count = data?.deleted_count ?? 0;
      toast.success(count === 1 ? '1 attachment deleted' : `${count} attachments deleted`);
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to delete attachments'),
  });
}

export function useRestoreAttachment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => restoreAttachment(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['attachments'] });
      toast.success('Attachment restored successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to restore attachment'),
  });
}

export function useDownloadAttachment() {
  return useMutation({
    mutationFn: (id: string) => downloadAttachment(id),
    onError: (error: Error) => toast.error(error.message || 'Failed to download attachment'),
  });
}

export function useResubmitAttachmentWebhook() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => resubmitAttachmentWebhook(id),
    onSuccess: () => {
      toast.success('Webhook resubmitted successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to resubmit webhook'),
  });
}
