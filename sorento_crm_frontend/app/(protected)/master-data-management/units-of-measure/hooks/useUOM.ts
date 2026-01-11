import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import { getUOMs, getUOM, createUOM, updateUOM, deleteUOM } from '../services/uomService';
import type { UOMFormData } from '../types/uom.types';

export function useUOMs(params: DataGridApiFetchParams) {
  return useQuery({
    queryKey: ['uoms', params.pageIndex, params.pageSize, params.sorting, params.searchQuery],
    queryFn: () => getUOMs(params),
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

export function useUOM(id: string | null) {
  return useQuery({
    queryKey: ['uom', id],
    queryFn: () => {
      if (!id) throw new Error('UOM ID is required');
      return getUOM(id);
    },
    enabled: !!id,
    retry: 1,
  });
}

export function useCreateUOM() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: UOMFormData) => createUOM(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['uoms'] });
      queryClient.invalidateQueries({ queryKey: ['uom-select'] });
      toast.success('UOM created successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to create UOM'),
  });
}

export function useUpdateUOM() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<UOMFormData> }) => updateUOM(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['uoms'] });
      queryClient.invalidateQueries({ queryKey: ['uom'] });
      queryClient.invalidateQueries({ queryKey: ['uom-select'] });
      toast.success('UOM updated successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to update UOM'),
  });
}

export function useDeleteUOM() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteUOM(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['uoms'] });
      queryClient.invalidateQueries({ queryKey: ['uom-select'] });
      toast.success('UOM deleted successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to delete UOM'),
  });
}
