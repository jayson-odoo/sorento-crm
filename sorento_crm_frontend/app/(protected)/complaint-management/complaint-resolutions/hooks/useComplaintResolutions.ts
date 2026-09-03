import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import {
  getComplaintResolutions,
  getComplaintResolutionsSelect,
  getComplaintResolution,
  createComplaintResolution,
  updateComplaintResolution,
  deleteComplaintResolution,
} from '../services/complaintResolutionService';
import type { ComplaintResolutionFormData } from '../types/complaintResolution.types';
import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';

export function useComplaintResolutions(params: DataGridApiFetchParams) {
  return useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: [
      'complaint-resolutions',
      params.pageIndex,
      params.pageSize,
      params.sorting,
      params.searchQuery,
    ],
    queryFn: () => getComplaintResolutions(params),
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    retry: 1,
  });
}

export function useComplaintResolution(id: string | null) {
  return useQuery({
    queryKey: ['complaint-resolution', id],
    queryFn: () => {
      if (!id) throw new Error('Resolution ID is required');
      return getComplaintResolution(id);
    },
    enabled: !!id,
    retry: 1,
  });
}

export function useComplaintResolutionsSelect(query?: string) {
  return useQuery({
    queryKey: ['complaint-resolutions-select', query ?? ''],
    queryFn: () => getComplaintResolutionsSelect(query),
    staleTime: 1000 * 60 * 5,
  });
}

export function useCreateComplaintResolution() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: ComplaintResolutionFormData) => createComplaintResolution(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['complaint-resolutions'] });
      queryClient.invalidateQueries({ queryKey: ['complaint-resolutions-select'] });
      toast.success('Resolution created');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to create resolution'),
  });
}

export function useUpdateComplaintResolution() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<ComplaintResolutionFormData> }) =>
      updateComplaintResolution(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['complaint-resolutions'] });
      queryClient.invalidateQueries({ queryKey: ['complaint-resolution'] });
      queryClient.invalidateQueries({ queryKey: ['complaint-resolutions-select'] });
      toast.success('Resolution updated');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to update resolution'),
  });
}

export function useDeleteComplaintResolution() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteComplaintResolution(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['complaint-resolutions'] });
      queryClient.invalidateQueries({ queryKey: ['complaint-resolutions-select'] });
      toast.success('Resolution deleted');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to delete resolution'),
  });
}
