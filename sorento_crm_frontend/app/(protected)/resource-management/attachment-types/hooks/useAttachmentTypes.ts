import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import { getAttachmentTypes, getAttachmentType, createAttachmentType, updateAttachmentType, deleteAttachmentType } from '../services/attachmentTypeService';
import type { AttachmentTypeFormData } from '../types/attachmentType.types';
import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';

export function useAttachmentTypes(params: DataGridApiFetchParams) {
  return useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: ['attachment-types', params.pageIndex, params.pageSize, params.sorting, params.searchQuery],
    queryFn: () => getAttachmentTypes(params),
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    retry: 1,
  });
}

export function useAttachmentType(id: string | null) {
  return useQuery({
    queryKey: ['attachment-type', id],
    queryFn: () => {
      if (!id) throw new Error('Attachment type ID is required');
      return getAttachmentType(id);
    },
    enabled: !!id,
    retry: 1,
  });
}

export function useCreateAttachmentType() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: AttachmentTypeFormData) => createAttachmentType(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['attachment-types'] });
      toast.success('Attachment type created successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to create attachment type'),
  });
}

export function useUpdateAttachmentType() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<AttachmentTypeFormData> }) => updateAttachmentType(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['attachment-types'] });
      queryClient.invalidateQueries({ queryKey: ['attachment-type'] });
      toast.success('Attachment type updated successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to update attachment type'),
  });
}

export function useDeleteAttachmentType() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteAttachmentType(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['attachment-types'] });
      toast.success('Attachment type deleted successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to delete attachment type'),
  });
}
