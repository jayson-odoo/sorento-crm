import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import {
  getTaxEntities,
  getTaxEntity,
  annotateTaxEntity,
} from '../services/taxEntityService';
import type { MirrorAnnotationPayload } from '../types/taxEntity.types';

export function useTaxEntities(params: DataGridApiFetchParams) {
  return useQuery({
    queryKey: ['tax-entities', params.pageIndex, params.pageSize, params.sorting, params.searchQuery],
    queryFn: () => getTaxEntities(params),
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

export function useTaxEntity(id: string | null) {
  return useQuery({
    queryKey: ['tax-entity', id],
    queryFn: () => {
      if (!id) throw new Error('Tax entity ID is required');
      return getTaxEntity(id);
    },
    enabled: !!id,
    retry: 1,
  });
}

export function useAnnotateTaxEntity() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: MirrorAnnotationPayload }) =>
      annotateTaxEntity(id, data),
    onSuccess: (_res, { id }) => {
      queryClient.invalidateQueries({ queryKey: ['tax-entities'] });
      queryClient.invalidateQueries({ queryKey: ['tax-entity', id] });
      toast.success('Note saved');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to save note'),
  });
}
