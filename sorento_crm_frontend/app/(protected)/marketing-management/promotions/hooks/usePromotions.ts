import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import {
  getPromotions,
  getPromotion,
  createPromotion,
  updatePromotion,
  deletePromotion,
  bulkDeletePromotions,
  bulkUpdateAccessLevels,
  getPromotionProducts,
  addPromotionProduct,
  removePromotionProduct,
  updatePromotionProductPrice,
  createPromotionGroup,
  updatePromotionGroup,
  deletePromotionGroup,
} from '../services/promotionService';
import type { PromotionFormData } from '../types/promotion.types';

export function usePromotions(params: DataGridApiFetchParams & { promo_type?: string; status?: string; date_from?: string; date_to?: string; user_type?: string }) {
  return useQuery({
    queryKey: ['promotions', params.pageIndex, params.pageSize, params.sorting, params.searchQuery, params.promo_type, params.status, params.date_from, params.date_to, params.user_type],
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

export function useBulkDeletePromotions() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (ids: string[]) => bulkDeletePromotions(ids),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['promotions'] });
      toast.success(result?.message ?? `${result?.deleted_count ?? 0} promotion(s) deleted`);
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to bulk delete promotions'),
  });
}

export function useBulkUpdatePromotionAccessLevels() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ ids, access_levels }: { ids: string[]; access_levels: string[] }) =>
      bulkUpdateAccessLevels(ids, access_levels),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['promotions'] });
      toast.success(result?.message ?? `Access levels set for ${result?.updated_count ?? 0} promotion(s).`);
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to update access levels'),
  });
}

export function useCreatePromotionGroup() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      promotionId,
      data,
    }: {
      promotionId: string;
      data: {
        group_name: string;
        sort_order?: number | null;
        foc_tiers?: { purchase_quantity: number; foc_quantity: number }[] | null;
        purchase_quantity_for_foc?: number | null;
        foc_quantity?: number | null;
      };
    }) => createPromotionGroup(promotionId, data),
    onSuccess: (_, v) => {
      queryClient.invalidateQueries({ queryKey: ['promotion', v.promotionId] });
      queryClient.invalidateQueries({ queryKey: ['promotion-products', v.promotionId] });
      queryClient.invalidateQueries({ queryKey: ['promotions'] });
      toast.success('Promotion group created');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to create group'),
  });
}

export function useUpdatePromotionGroup() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      promotionId,
      groupId,
      data,
    }: {
      promotionId: string;
      groupId: string;
      data: {
        group_name?: string;
        sort_order?: number | null;
        foc_tiers?: { purchase_quantity: number; foc_quantity: number }[] | null;
        purchase_quantity_for_foc?: number | null;
        foc_quantity?: number | null;
      };
    }) => updatePromotionGroup(promotionId, groupId, data),
    onSuccess: (_, v) => {
      queryClient.invalidateQueries({ queryKey: ['promotion', v.promotionId] });
      queryClient.invalidateQueries({ queryKey: ['promotions'] });
      toast.success('Promotion group updated');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to update group'),
  });
}

export function useDeletePromotionGroup() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ promotionId, groupId }: { promotionId: string; groupId: string }) =>
      deletePromotionGroup(promotionId, groupId),
    onSuccess: (result, v) => {
      queryClient.invalidateQueries({ queryKey: ['promotion', v.promotionId] });
      queryClient.invalidateQueries({ queryKey: ['promotion-products', v.promotionId] });
      queryClient.invalidateQueries({ queryKey: ['promotions'] });
      const n = result?.deleted_product_lines;
      toast.success(
        typeof n === 'number' && n > 0
          ? `Group deleted (${n} product line(s) removed)`
          : 'Promotion group deleted',
      );
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to delete group'),
  });
}

export function useAddPromotionProduct() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      promotionId,
      productId,
      promotionPrice,
      promotionGroupId,
      dealerDiscountPercent,
    }: {
      promotionId: string;
      productId: string;
      promotionPrice?: number;
      promotionGroupId?: string;
      dealerDiscountPercent?: number | null;
    }) =>
      addPromotionProduct(promotionId, productId, promotionPrice, promotionGroupId, dealerDiscountPercent),
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
    mutationFn: ({ promotionId, lineId }: { promotionId: string; lineId: string }) =>
      removePromotionProduct(promotionId, lineId),
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
    mutationFn: ({
      promotionId,
      lineId,
      promotionPrice,
      dealerDiscountPercent,
    }: {
      promotionId: string;
      lineId: string;
      promotionPrice: number;
      dealerDiscountPercent?: number | null;
    }) => updatePromotionProductPrice(promotionId, lineId, promotionPrice, dealerDiscountPercent),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['promotion-products', variables.promotionId] });
      queryClient.invalidateQueries({ queryKey: ['promotion', variables.promotionId] });
      toast.success('Promotion product updated successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to update promotion product price'),
  });
}
