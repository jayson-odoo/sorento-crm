import { useQuery, useMutation, useQueryClient, type QueryKey } from '@tanstack/react-query';
import { toast } from '@/lib/toast';

import type { ListPagerParams, ListPagerPage } from '@/hooks/useListPager';
import type { DataGridApiResponse } from '@/components/ui/data-grid';
import { decodeAdvancedFilter } from '@/lib/listNavQuery';
import {
  postListQuerySearch,
  type ListQueryFilterGroup,
} from '@/lib/list-query/listQueryService';

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
  updatePromotionProductPrice,
  createPromotionGroup,
  updatePromotionGroup,
  compilePromotionsPdf,
  type PromotionsListParams,
} from '../services/promotionService';
import { resubmitAttachmentWebhook } from '@/app/(protected)/resource-management/attachments/services/attachmentService';
import type { Promotion, PromotionFormData } from '../types/promotion.types';
import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';


/** The list params, plus the advanced filter that decides which endpoint serves them. */
export type PromotionsPageParams = PromotionsListParams & {
  advancedFilter?: ListQueryFilterGroup;
};

/**
 * The list's React Query key. The detail page's pager rebuilds the SAME key from
 * the URL, so it reads the page the list already fetched.
 *
 * Every value that narrows the set is in here, including the cleanup filter, the
 * expiry-batch deep link and the advanced filter. `PromotionsList` built its own
 * key inline for a while and the two drifted: the pager missed the cache on every
 * promotion, fetched its own page, and paged a different set.
 */
export function promotionsListQueryKey(params: PromotionsPageParams): QueryKey {
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
    params.attachment_state,
    params.expiry_notify_batch_id,
    params.advancedFilter,
  ];
}

/** GET for a plain list, POST list-query when an advanced filter is on. */
export function fetchPromotionsPage(
  params: PromotionsPageParams,
): Promise<DataGridApiResponse<Promotion>> {
  if (params.advancedFilter) {
    return postListQuerySearch<Promotion>({
      resource: 'promotions',
      filter: params.advancedFilter,
      page: params.pageIndex + 1,
      limit: params.pageSize,
      sort: params.sorting?.[0]?.id || 'created_at',
      dir: params.sorting?.[0]?.desc ? 'desc' : 'asc',
      quick_search: params.searchQuery || undefined,
      promotion_status: params.status,
      promotion_access_level: params.user_type,
    });
  }
  return getPromotions(params);
}

/** The list query a detail URL describes, in the shape the list passes. */
export function promotionsListParamsFromUrl(
  params: ListPagerParams,
): PromotionsPageParams {
  return {
    pageIndex: params.pageIndex,
    pageSize: params.pageSize,
    sorting: params.sorting,
    searchQuery: params.searchQuery,
    /**
     * The LIST's default, not the parser's absence.
     *
     * "All" is not a narrowing, so the row href does not write it; but the list
     * passes `status: 'all'` and the backend, given no status at all, returns
     * ACTIVE promotions only. Restoring `undefined` here paged four active rows
     * beside a list of thirty-two, and hid the pager outright on any promotion
     * that had expired.
     */
    status: params.filters.status ?? 'all',
    date_from: params.filters.date_from,
    date_to: params.filters.date_to,
    user_type: params.filters.user_type,
    attachment_state: params.filters
      .attachment_state as PromotionsListParams['attachment_state'],
    expiry_notify_batch_id: params.filters.expiry_notify_batch_id,
    advancedFilter:
      decodeAdvancedFilter<ListQueryFilterGroup>(params.filters.advFilter) ?? undefined,
  };
}

/** The pager's two hooks into the promotions list. */
export const promotionsPagerQuery = {
  listQueryKey: (params: ListPagerParams): QueryKey =>
    promotionsListQueryKey(promotionsListParamsFromUrl(params)),
  fetchPage: (params: ListPagerParams): Promise<ListPagerPage> =>
    fetchPromotionsPage(promotionsListParamsFromUrl(params)),
};

export function usePromotions(params: PromotionsPageParams) {
  return useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: promotionsListQueryKey(params),
    queryFn: () => fetchPromotionsPage(params),
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
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
