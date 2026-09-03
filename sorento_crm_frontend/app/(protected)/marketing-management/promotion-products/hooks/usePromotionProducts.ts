import { useQuery } from '@tanstack/react-query';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import { getPromotionProductsList } from '../services/promotionProductService';
import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';

export function usePromotionProductsList(params: DataGridApiFetchParams) {
  return useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: ['promotion-products-list', params.pageIndex, params.pageSize, params.sorting, params.searchQuery],
    queryFn: () => getPromotionProductsList(params),
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    retry: 1,
  });
}
