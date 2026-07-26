import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import {
  getQuotations,
  getQuotation,
  annotateQuotation,
} from '../services/quotationService';
import type { MirrorAnnotationPayload } from '../types/quotation.types';

export function useQuotations(params: DataGridApiFetchParams) {
  return useQuery({
    queryKey: ['quotations', params.pageIndex, params.pageSize, params.sorting, params.searchQuery],
    queryFn: () => getQuotations(params),
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

export function useQuotation(id: string | null) {
  return useQuery({
    queryKey: ['quotation', id],
    queryFn: () => {
      if (!id) throw new Error('Quotation ID is required');
      return getQuotation(id);
    },
    enabled: !!id,
    retry: 1,
  });
}

export function useAnnotateQuotation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: MirrorAnnotationPayload }) =>
      annotateQuotation(id, data),
    onSuccess: (_res, { id }) => {
      queryClient.invalidateQueries({ queryKey: ['quotations'] });
      queryClient.invalidateQueries({ queryKey: ['quotation', id] });
      toast.success('Note saved');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to save note'),
  });
}
