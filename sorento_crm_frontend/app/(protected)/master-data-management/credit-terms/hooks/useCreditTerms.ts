import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import {
  getCreditTerms,
  getCreditTerm,
  annotateCreditTerm,
} from '../services/creditTermService';
import type { MirrorAnnotationPayload } from '../types/creditTerm.types';

export function useCreditTerms(params: DataGridApiFetchParams) {
  return useQuery({
    queryKey: ['credit-terms', params.pageIndex, params.pageSize, params.sorting, params.searchQuery],
    queryFn: () => getCreditTerms(params),
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

export function useCreditTerm(id: string | null) {
  return useQuery({
    queryKey: ['credit-term', id],
    queryFn: () => {
      if (!id) throw new Error('Credit term ID is required');
      return getCreditTerm(id);
    },
    enabled: !!id,
    retry: 1,
  });
}

export function useAnnotateCreditTerm() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: MirrorAnnotationPayload }) =>
      annotateCreditTerm(id, data),
    onSuccess: (_res, { id }) => {
      queryClient.invalidateQueries({ queryKey: ['credit-terms'] });
      queryClient.invalidateQueries({ queryKey: ['credit-term', id] });
      toast.success('Note saved');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to save note'),
  });
}
