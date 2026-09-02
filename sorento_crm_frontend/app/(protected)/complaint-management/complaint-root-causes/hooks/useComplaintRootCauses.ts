import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import {
  getComplaintRootCauses,
  getComplaintRootCausesSelect,
  getComplaintRootCause,
  createComplaintRootCause,
  updateComplaintRootCause,
  deleteComplaintRootCause,
} from '../services/complaintRootCauseService';
import type { ComplaintRootCauseFormData } from '../types/complaintRootCause.types';

export function useComplaintRootCauses(params: DataGridApiFetchParams) {
  return useQuery({
    queryKey: [
      'complaint-root-causes',
      params.pageIndex,
      params.pageSize,
      params.sorting,
      params.searchQuery,
    ],
    queryFn: () => getComplaintRootCauses(params),
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

export function useComplaintRootCause(id: string | null) {
  return useQuery({
    queryKey: ['complaint-root-cause', id],
    queryFn: () => {
      if (!id) throw new Error('Root cause ID is required');
      return getComplaintRootCause(id);
    },
    enabled: !!id,
    retry: 1,
  });
}

export function useComplaintRootCausesSelect(query?: string) {
  return useQuery({
    queryKey: ['complaint-root-causes-select', query ?? ''],
    queryFn: () => getComplaintRootCausesSelect(query),
    staleTime: 1000 * 60 * 5,
    refetchOnWindowFocus: false,
  });
}

export function useCreateComplaintRootCause() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: ComplaintRootCauseFormData) => createComplaintRootCause(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['complaint-root-causes'] });
      queryClient.invalidateQueries({ queryKey: ['complaint-root-causes-select'] });
      toast.success('Root cause created');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to create root cause'),
  });
}

export function useUpdateComplaintRootCause() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<ComplaintRootCauseFormData> }) =>
      updateComplaintRootCause(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['complaint-root-causes'] });
      queryClient.invalidateQueries({ queryKey: ['complaint-root-cause'] });
      queryClient.invalidateQueries({ queryKey: ['complaint-root-causes-select'] });
      toast.success('Root cause updated');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to update root cause'),
  });
}

export function useDeleteComplaintRootCause() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteComplaintRootCause(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['complaint-root-causes'] });
      queryClient.invalidateQueries({ queryKey: ['complaint-root-causes-select'] });
      toast.success('Root cause deleted');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to delete root cause'),
  });
}
