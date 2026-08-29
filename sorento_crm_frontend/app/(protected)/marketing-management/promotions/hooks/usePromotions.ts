import { useQuery, useMutation, useQueryClient, type QueryKey } from '@tanstack/react-query';
import { toast } from 'sonner';

import type { ListPagerParams, ListPagerPage } from '@/hooks/useListPager';

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
  compilePromotionsPdf,
  type PromotionsListParams,
} from '../services/promotionService';
import { resubmitAttachmentWebhook } from '@/app/(protected)/resource-management/attachments/services/attachmentService';
import type { PromotionFormData } from '../types/promotion.types';


/**
 * The list's React Query key. The detail page's pager rebuilds the SAME key from
 * the URL, so it reads the page the list already fetched.
 */
export function promotionsListQueryKey(params: PromotionsListParams): QueryKey {
  return [
    'promotions',
    params.pageIndex,
    params.pageSize,
    params.sorting,
    params.searchQuery,
    params.status,
    params.date_from,
    params.date_to,
    params.user_type,
  ];
}

/** The list query a detail URL describes, in the shape the list passes. */
export function promotionsListParamsFromUrl(
  params: ListPagerParams,
): PromotionsListParams {
  return {
    pageIndex: params.pageIndex,
    pageSize: params.pageSize,
    sorting: params.sorting,
    searchQuery: params.searchQuery,
    status: params.filters.status,
    date_from: params.filters.date_from,
    date_to: params.filters.date_to,
    user_type: params.filters.user_type,
    expiry_notify_batch_id: params.filters.expiry_notify_batch_id,
    attachment_state: params.filters
      .attachment_state as PromotionsListParams['attachment_state'],
  };
}

/** The pager's two hooks into the promotions list. */
export const promotionsPagerQuery = {
  listQueryKey: (params: ListPagerParams): QueryKey =>
    promotionsListQueryKey(promotionsListParamsFromUrl(params)),
  fetchPage: (params: ListPagerParams): Promise<ListPagerPage> =>
    getPromotions(promotionsListParamsFromUrl(params)),
};

export function usePromotions(params: PromotionsListParams) {
  return useQuery({
    queryKey: promotionsListQueryKey(params),
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

export function useCompilePromotionsPdf() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (promotionIds: string[]) => compilePromotionsPdf(promotionIds),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['my-downloads'] });
      toast.success('Preparing PDF… it will appear in My Downloads.');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to start PDF export'),
  });
}

/**
 * Re-run AI extraction on promotion flyers by resubmitting their attachment webhooks.
 *
 * Sequential on purpose: every resubmit starts a Gemini extraction on the n8n side,
 * and firing a whole page of selections at once would stampede that workflow. One
 * failure does not abort the rest - the caller reports the tally.
 */
export function useResubmitPromotionFlyers() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (attachmentIds: string[]) => {
      let succeeded = 0;
      const failures: string[] = [];
      for (const attachmentId of attachmentIds) {
        try {
          await resubmitAttachmentWebhook(attachmentId);
          succeeded += 1;
        } catch (error) {
          failures.push(error instanceof Error ? error.message : 'Unknown error');
        }
      }
      return { succeeded, failures };
    },
    onSuccess: ({ succeeded, failures }) => {
      if (succeeded > 0) {
        queryClient.invalidateQueries({ queryKey: ['promotions'] });
        toast.success(
          `${succeeded} flyer(s) sent for re-extraction. Products update once n8n finishes.`,
        );
      }
      if (failures.length > 0) {
        toast.error(`${failures.length} flyer(s) could not be resubmitted: ${failures[0]}`);
      }
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to resubmit flyers'),
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
      listPrice,
    }: {
      promotionId: string;
      lineId: string;
      promotionPrice: number;
      dealerDiscountPercent: number | null;
      listPrice: number;
    }) =>
      updatePromotionProductPrice(promotionId, lineId, {
        promotionPrice,
        dealerDiscountPercent,
        listPrice,
      }),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['promotion-products', variables.promotionId] });
      queryClient.invalidateQueries({ queryKey: ['promotion', variables.promotionId] });
      queryClient.invalidateQueries({ queryKey: ['products'] });
      toast.success('Promotion product updated successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to update promotion product price'),
  });
}
