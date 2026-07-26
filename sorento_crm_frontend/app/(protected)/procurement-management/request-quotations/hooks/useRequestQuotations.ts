import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import {
  getRequestQuotations,
  getRequestQuotation,
  annotateRequestQuotation,
} from '../services/requestQuotationService';
import type { MirrorAnnotationPayload } from '../types/requestQuotation.types';

export function useRequestQuotations(params: DataGridApiFetchParams) {
  return useQuery({
    queryKey: [
      'request-quotations',
      params.pageIndex,
      params.pageSize,
      params.sorting,
      params.searchQuery,
    ],
    queryFn: () => getRequestQuotations(params),
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

export function useRequestQuotation(id: string | null) {
  return useQuery({
    queryKey: ['request-quotation', id],
    queryFn: () => {
      if (!id) throw new Error('Request quotation ID is required');
      return getRequestQuotation(id);
    },
    enabled: !!id,
    retry: 1,
  });
}

export function useAnnotateRequestQuotation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: MirrorAnnotationPayload }) =>
      annotateRequestQuotation(id, data),
    onSuccess: (_res, { id }) => {
      queryClient.invalidateQueries({ queryKey: ['request-quotations'] });
      queryClient.invalidateQueries({ queryKey: ['request-quotation', id] });
      toast.success('Note saved');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to save note'),
  });
}
