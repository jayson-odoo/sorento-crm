import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import { getTaxCodes, getTaxCode, annotateTaxCode } from '../services/taxCodeService';
import type { MirrorAnnotationPayload } from '../types/taxCode.types';

export function useTaxCodes(params: DataGridApiFetchParams) {
  return useQuery({
    queryKey: ['tax-codes', params.pageIndex, params.pageSize, params.sorting, params.searchQuery],
    queryFn: () => getTaxCodes(params),
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

export function useTaxCode(id: string | null) {
  return useQuery({
    queryKey: ['tax-code', id],
    queryFn: () => {
      if (!id) throw new Error('Tax code ID is required');
      return getTaxCode(id);
    },
    enabled: !!id,
    retry: 1,
  });
}

export function useAnnotateTaxCode() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: MirrorAnnotationPayload }) =>
      annotateTaxCode(id, data),
    onSuccess: (_res, { id }) => {
      queryClient.invalidateQueries({ queryKey: ['tax-codes'] });
      queryClient.invalidateQueries({ queryKey: ['tax-code', id] });
      toast.success('Note saved');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to save note'),
  });
}
