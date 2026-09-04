import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import {
  createPromotionType,
  getPromotionType,
  getPromotionTypes,
  updatePromotionType,
} from '../services/promotionTypeService';
import type { PromotionTypeFormData } from '../types/promotionType.types';

export function usePromotionTypes() {
  return useQuery({
    queryKey: ['promotion-types'],
    queryFn: getPromotionTypes,
    staleTime: 1000 * 60 * 5,
    retry: 1,
  });
}

export function usePromotionType(id: string | null) {
  return useQuery({
    queryKey: ['promotion-type', id],
    queryFn: () => {
      if (!id) throw new Error('Promotion type id is required');
      return getPromotionType(id);
    },
    enabled: !!id,
    retry: false,
  });
}

export function useCreatePromotionType() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: PromotionTypeFormData) => createPromotionType(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['promotion-types'] });
      // The promotions list renders the type name, so it goes stale too.
      queryClient.invalidateQueries({ queryKey: ['promotions'] });
      toast.success('Promotion type created');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to create promotion type'),
  });
}

export function useUpdatePromotionType() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<PromotionTypeFormData> }) =>
      updatePromotionType(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['promotion-types'] });
      queryClient.invalidateQueries({ queryKey: ['promotion-type'] });
      queryClient.invalidateQueries({ queryKey: ['promotions'] });
      toast.success('Promotion type updated');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to update promotion type'),
  });
}

