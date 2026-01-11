import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import { getPromotions, getPromotion, createPromotion, updatePromotion, deletePromotion, getPromotionProducts, addPromotionProduct, removePromotionProduct, updatePromotionProductPrice } from '../services/promotionService';
import type { PromotionFormData } from '../types/promotion.types';

export function usePromotions(params: DataGridApiFetchParams & { promo_type?: string; status?: string; date_from?: string; date_to?: string }) {
  return useQuery({
    queryKey: ['promotions', params.pageIndex, params.pageSize, params.sorting, params.searchQuery, params.promo_type, params.status, params.date_from, params.date_to],
    queryFn: () => getPromotions(params),
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

export function usePromotion(id: string | null) {
  return useQuery({
    queryKey: ['promotion', id],
    queryFn: () => {
      if (!id) throw new Error('Promotion ID is required');
      return getPromotion(id);
    },
    enabled: !!id,
    retry: 1,
  });
}

export function usePromotionProducts(promotionId: string | null) {
  return useQuery({
    queryKey: ['promotion-products', promotionId],
    queryFn: () => {
      if (!promotionId) throw new Error('Promotion ID is required');
      return getPromotionProducts(promotionId);
    },
    enabled: !!promotionId,
    retry: 1,
  });
}

export function useCreatePromotion() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: PromotionFormData) => createPromotion(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['promotions'] });
      toast.success('Promotion created successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to create promotion'),
  });
}

export function useUpdatePromotion() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<PromotionFormData> }) => updatePromotion(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['promotions'] });
      queryClient.invalidateQueries({ queryKey: ['promotion'] });
      toast.success('Promotion updated successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to update promotion'),
  });
}

export function useDeletePromotion() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deletePromotion(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['promotions'] });
      toast.success('Promotion deleted successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to delete promotion'),
  });
}

export function useAddPromotionProduct() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ promotionId, productId, promotionPrice }: { promotionId: string; productId: string; promotionPrice?: number }) =>
      addPromotionProduct(promotionId, productId, promotionPrice),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['promotion-products', variables.promotionId] });
      queryClient.invalidateQueries({ queryKey: ['promotion', variables.promotionId] });
      toast.success('Product added to promotion successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to add product to promotion'),
  });
}

export function useRemovePromotionProduct() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ promotionId, productId }: { promotionId: string; productId: string }) =>
      removePromotionProduct(promotionId, productId),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['promotion-products', variables.promotionId] });
      queryClient.invalidateQueries({ queryKey: ['promotion', variables.promotionId] });
      toast.success('Product removed from promotion successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to remove product from promotion'),
  });
}

export function useUpdatePromotionProductPrice() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ promotionId, productId, promotionPrice }: { promotionId: string; productId: string; promotionPrice: number }) =>
      updatePromotionProductPrice(promotionId, productId, promotionPrice),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['promotion-products', variables.promotionId] });
      toast.success('Promotion product price updated successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to update promotion product price'),
  });
}
