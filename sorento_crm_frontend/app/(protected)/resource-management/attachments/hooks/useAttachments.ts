import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import { getAttachments, uploadAttachment, deleteAttachment, restoreAttachment, downloadAttachment, getAttachmentMetadata, checkDuplicateByHash } from '../services/attachmentService';

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
    mutationFn: ({ file, entityType, entityId, description }: { file: File; entityType: string; entityId: string; description?: string }) =>
      uploadAttachment(file, entityType, entityId, description),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['attachments'] });
      toast.success('File uploaded successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to upload file'),
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
