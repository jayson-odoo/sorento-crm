import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import {
  getPaymentMethods,
  getPaymentMethod,
  annotatePaymentMethod,
} from '../services/paymentMethodService';
import type { MirrorAnnotationPayload } from '../types/paymentMethod.types';

export function usePaymentMethods(params: DataGridApiFetchParams) {
  return useQuery({
    queryKey: ['payment-methods', params.pageIndex, params.pageSize, params.sorting, params.searchQuery],
    queryFn: () => getPaymentMethods(params),
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

export function usePaymentMethod(id: string | null) {
  return useQuery({
    queryKey: ['payment-method', id],
    queryFn: () => {
      if (!id) throw new Error('Payment method ID is required');
      return getPaymentMethod(id);
    },
    enabled: !!id,
    retry: 1,
  });
}

export function useAnnotatePaymentMethod() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: MirrorAnnotationPayload }) =>
      annotatePaymentMethod(id, data),
    onSuccess: (_res, { id }) => {
      queryClient.invalidateQueries({ queryKey: ['payment-methods'] });
      queryClient.invalidateQueries({ queryKey: ['payment-method', id] });
      toast.success('Note saved');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to save note'),
  });
}
