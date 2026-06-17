import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import type { QueryKey } from '@tanstack/react-query';
import { toast } from 'sonner';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import { getAttachments, uploadAttachment, updateAttachment, deleteAttachment, bulkDeleteAttachments, archiveAttachment, bulkArchiveAttachments, restoreAttachment, bulkRestoreAttachments, downloadAttachment, resubmitAttachmentWebhook, reorderAttachments, bulkImportAttachments, bulkMoveAttachments } from '../services/attachmentService';
import type { Attachment } from '../types/attachment.types';
import { getDirectoryTree, createDirectory, updateDirectory, moveDirectory, deleteDirectory, restoreDirectory, permanentDeleteDirectory } from '../services/directoryService';
import { apiFetch } from '@/lib/api';
import type { AttachmentType } from '../../attachment-types/types/attachmentType.types';

export function useAttachments(params: DataGridApiFetchParams & { entity_type?: string; file_type?: string; attachment_type_id?: string; upload_date_from?: string; upload_date_to?: string; uploaded_at_from?: string; uploaded_at_to?: string; uploaded_by?: string; is_deleted?: boolean; virus_status?: string; directory_id?: string | null; link_status?: 'linked' | 'unlinked'; storage_status?: 'accessible' | 'missing' | 'unchecked'; resolve_signed_urls?: boolean; access_levels?: string[]; access_levels_match?: 'any' | 'all' | 'exact' }) {
  const accessLevelsKey = (params.access_levels ?? []).slice().sort().join(',');
  return useQuery({
    queryKey: ['attachments', params.pageIndex, params.pageSize, params.sorting, params.searchQuery, params.entity_type, params.file_type, params.attachment_type_id, params.upload_date_from, params.upload_date_to, params.uploaded_at_from, params.uploaded_at_to, params.uploaded_by, params.is_deleted, params.virus_status, params.directory_id, params.link_status, params.resolve_signed_urls, accessLevelsKey, params.access_levels_match ?? 'any', params.storage_status ?? '__all__'],
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
    mutationFn: ({
      file,
      attachmentTypeId,
      entityType,
      entityId,
      accessLevels,
      directoryId,
      targetEntityType,
      targetFieldKeys,
      onConflict,
      uploadBatchId,
    }: {
      file: File;
      attachmentTypeId?: string | null;
      entityType?: string;
      entityId?: string;
      accessLevels?: string[];
      directoryId?: string | null;
      targetEntityType?: string | null;
      targetFieldKeys?: string[] | null;
      onConflict?: 'copy' | 'replace';
      uploadBatchId?: string;
    }) =>
      uploadAttachment(file, {
        attachmentTypeId: attachmentTypeId ?? undefined,
        entityType,
        entityId,
        accessLevels,
        directoryId,
        targetEntityType,
        targetFieldKeys,
        onConflict,
        uploadBatchId,
      }),
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

export function useUpdateAttachment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ attachmentId, data }: { attachmentId: string; data: { directory_id?: string | null; description?: string | null; access_levels?: string[] | null; stored_filename?: string } }) =>
      updateAttachment(attachmentId, data),
    onSuccess: (_, { attachmentId }) => {
      queryClient.invalidateQueries({ queryKey: ['attachments'] });
      queryClient.invalidateQueries({ queryKey: ['attachment-metadata', attachmentId] });
      queryClient.invalidateQueries({ queryKey: ['product-attachments-by-product'] });
      queryClient.invalidateQueries({ queryKey: ['promotion-attachments-by-promotion'] });
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to update attachment'),
  });
}

export function useBulkMoveAttachments() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ attachmentIds, directoryId }: { attachmentIds: string[]; directoryId: string | null }) =>
      bulkMoveAttachments(attachmentIds, directoryId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['attachments'] });
      queryClient.invalidateQueries({ queryKey: ['attachment-directories-tree'] });
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to move attachments'),
  });
}

const ATTACHMENTS_QUERY_KEY_DIRECTORY_INDEX = 11;

export function useReorderAttachments() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ attachmentIds, directoryId }: { attachmentIds: string[]; directoryId?: string | null }) =>
      reorderAttachments(attachmentIds, directoryId),
    onMutate: ({ attachmentIds, directoryId }) => {
      // Update cache synchronously so the list doesn't snap back before re-render
      queryClient.cancelQueries({ queryKey: ['attachments'] });
      const queries = queryClient.getQueriesData<{ data?: Attachment[]; pagination?: unknown }>({
        queryKey: ['attachments'],
      });
      const previous: Array<[QueryKey, unknown]> = [];
      for (const [queryKey, data] of queries) {
        const keyDir = (queryKey as unknown[])[ATTACHMENTS_QUERY_KEY_DIRECTORY_INDEX];
        const matches =
          (keyDir === undefined && (directoryId === undefined || directoryId === null)) ||
          keyDir === directoryId;
        if (!matches || !data?.data) continue;
        previous.push([queryKey, data]);
        const reordered = attachmentIds
          .map((id) => data.data!.find((a) => a.id === id))
          .filter((a): a is Attachment => a != null);
        const rest = data.data.filter((a) => !attachmentIds.includes(a.id));
        queryClient.setQueryData(queryKey, { ...data, data: [...reordered, ...rest] });
      }
      return { previous };
    },
    onError: (error: Error, _variables, context) => {
      if (context?.previous?.length) {
        context.previous.forEach(([queryKey, data]) => queryClient.setQueryData(queryKey, data));
      }
      toast.error(error.message || 'Failed to reorder');
    },
    onSuccess: () => {
      toast.success('Order updated');
    },
  });
}

export function useDeleteAttachment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteAttachment(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['attachments'] });
      toast.success('Attachment permanently deleted');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to delete attachment'),
  });
}

export function useArchiveAttachment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => archiveAttachment(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['attachments'] });
      toast.success('Attachment moved to trash');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to archive attachment'),
  });
}

export function useBulkArchiveAttachments() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (ids: string[]) => bulkArchiveAttachments(ids),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['attachments'] });
      const count = data?.archived_count ?? 0;
      toast.success(count === 1 ? '1 attachment moved to trash' : `${count} attachments moved to trash`);
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to archive attachments'),
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

export function useBulkRestoreAttachments() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (ids: string[]) => bulkRestoreAttachments(ids),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['attachments'] });
      const count = data?.restored_count ?? 0;
      toast.success(count === 1 ? '1 attachment restored' : `${count} attachments restored`);
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to restore attachments'),
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
    onSuccess: (_data, id) => {
      toast.success('Resubmitted successfully');
      // Refresh the sources behind IntegrationStatusChip so it flips to
      // "Processing" immediately instead of waiting for a modal remount:
      //   1. the upload-activity drawer feed (preferred chip source)
      //   2. the per-attachment integration_log fallback query
      queryClient.invalidateQueries({ queryKey: ['upload-activity'] });
      queryClient.invalidateQueries({
        queryKey: ['integration-log', 'latest', 'attachment', id],
      });
      queryClient.invalidateQueries({ queryKey: ['attachment-metadata', id] });
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to resubmit'),
  });
}

export function useBulkImportAttachment() {
  return useMutation({
    mutationFn: ({
      zipFile,
      attachmentTypeId,
      accessLevels,
      parentDirectoryId,
    }: {
      zipFile: File;
      attachmentTypeId: string;
      accessLevels?: string[];
      parentDirectoryId?: string | null;
    }) => bulkImportAttachments(zipFile, attachmentTypeId, accessLevels, parentDirectoryId),
    onSuccess: () => {
      toast.success('Import started. Processing in the background.');
    },
    onError: (error: Error) => toast.error(error.message || 'Bulk import failed'),
  });
}

export function useDirectoryTree(deleted = false) {
  return useQuery({
    queryKey: ['attachment-directories-tree', deleted],
    queryFn: () => getDirectoryTree(deleted),
    staleTime: 1000 * 60 * 2,
    gcTime: 1000 * 60 * 10,
  });
}

export function useRestoreDirectory() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => restoreDirectory(id),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['attachment-directories-tree'] });
      queryClient.invalidateQueries({ queryKey: ['attachments'] });
      const dirs = data?.directories_restored ?? 0;
      const atts = data?.attachments_restored ?? 0;
      toast.success(`Restored ${dirs} folder(s) and ${atts} attachment(s)`);
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to restore directory'),
  });
}

export function usePermanentDeleteDirectory() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => permanentDeleteDirectory(id),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['attachment-directories-tree'] });
      queryClient.invalidateQueries({ queryKey: ['attachments'] });
      const dirs = data?.directories_deleted ?? 0;
      const atts = data?.attachments_deleted ?? 0;
      toast.success(`Permanently deleted ${dirs} folder(s) and ${atts} attachment(s)`);
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to permanently delete directory'),
  });
}

export function useCreateDirectory() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ name, parentId }: { name: string; parentId?: string | null }) =>
      createDirectory(name, parentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['attachment-directories-tree'] });
      queryClient.invalidateQueries({ queryKey: ['attachments'] });
      toast.success('Folder created');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to create folder'),
  });
}

export function useUpdateDirectory() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: { name?: string; parent_id?: string | null; sort_order?: number | null } }) =>
      updateDirectory(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['attachment-directories-tree'] });
      queryClient.invalidateQueries({ queryKey: ['attachments'] });
      toast.success('Folder updated');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to update folder'),
  });
}

export function useMoveDirectory() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, parent_id, position }: { id: string; parent_id: string | null; position: number | null }) =>
      moveDirectory(id, { parent_id, position }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['attachment-directories-tree'] });
      queryClient.invalidateQueries({ queryKey: ['attachments'] });
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to move folder'),
  });
}

export function useDeleteDirectory() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteDirectory(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['attachment-directories-tree'] });
      queryClient.invalidateQueries({ queryKey: ['attachments'] });
      toast.success('Folder deleted');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to delete folder'),
  });
}
