import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import {
  getItemPackages,
  getItemPackage,
  annotateItemPackage,
} from '../services/itemPackageService';
import type { MirrorAnnotationPayload } from '../types/itemPackage.types';

export function useItemPackages(params: DataGridApiFetchParams) {
  return useQuery({
    queryKey: ['item-packages', params.pageIndex, params.pageSize, params.sorting, params.searchQuery],
    queryFn: () => getItemPackages(params),
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

export function useItemPackage(id: string | null) {
  return useQuery({
    queryKey: ['item-package', id],
    queryFn: () => {
      if (!id) throw new Error('Item package ID is required');
      return getItemPackage(id);
    },
    enabled: !!id,
    retry: 1,
  });
}

export function useAnnotateItemPackage() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: MirrorAnnotationPayload }) =>
      annotateItemPackage(id, data),
    onSuccess: (_res, { id }) => {
      queryClient.invalidateQueries({ queryKey: ['item-packages'] });
      queryClient.invalidateQueries({ queryKey: ['item-package', id] });
      toast.success('Note saved');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to save note'),
  });
}
