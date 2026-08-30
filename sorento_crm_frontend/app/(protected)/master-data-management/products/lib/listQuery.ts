/**
 * The products list query, in one place.
 *
 * The list and the detail page's pager MUST build the same React Query key for
 * the same page, or the pager misses the cache and refetches what the list is
 * already holding (see `hooks/useListPager.ts`). Both call the functions here,
 * and every filter that narrows the list is carried in the detail URL so the key
 * can be rebuilt from it.
 */

import type { QueryKey } from '@tanstack/react-query';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';
import { decodeAdvancedFilter } from '@/lib/listNavQuery';
import { postListQuerySearch } from '@/lib/list-query/listQueryService';
import type { ListQueryFilterGroup } from '@/lib/list-query/listQueryService';
import type { ListPagerParams, ListPagerPage } from '@/hooks/useListPager';
import { getProducts } from '../services/productService';
import type { ProductListItem } from '../types/product.types';

export type ProductsListParams = DataGridApiFetchParams & {
  category_id?: string;
  /** One brand id, or the comma-separated list a discontinued deep link carries. */
  brand_id?: string;
  status?: string;
  variant_filter?: 'base' | 'variant' | 'all';
  discontinued_batch_id?: string;
  /** The brand slice of a discontinued batch, when the recipient is scoped. */
  discontinued_brand_ids?: string;
  advancedFilter?: ListQueryFilterGroup | null;
};

export function productsListQueryKey(params: ProductsListParams): QueryKey {
  return [
    'products',
    params.pageIndex,
    params.pageSize,
    params.sorting,
    params.searchQuery,
    params.category_id,
    params.brand_id,
    params.status,
    params.variant_filter,
    params.advancedFilter,
    params.discontinued_batch_id,
    params.discontinued_brand_ids,
  ];
}

export function fetchProductsPage(
  params: ProductsListParams,
): Promise<DataGridApiResponse<ProductListItem>> {
  const sortField = params.sorting?.[0]?.id || '';
  const sortDirection = params.sorting?.[0]?.desc ? 'desc' : 'asc';

  if (params.advancedFilter) {
    return postListQuerySearch<ProductListItem>({
      resource: 'products',
      filter: params.advancedFilter,
      page: params.pageIndex + 1,
      limit: params.pageSize,
      sort: sortField || 'created_at',
      dir: sortDirection,
      quick_search: params.searchQuery || undefined,
      category_id: params.category_id,
      brand_id: params.brand_id,
      product_status:
        params.status && params.status !== 'all' ? params.status : undefined,
    });
  }

  return getProducts({
    pageIndex: params.pageIndex,
    pageSize: params.pageSize,
    sorting: params.sorting,
    searchQuery: params.searchQuery,
    ...(params.category_id ? { category_id: params.category_id } : {}),
    ...(params.brand_id ? { brand_id: params.brand_id } : {}),
    status: (params.status as 'active' | 'inactive' | 'all') ?? 'all',
    ...(params.variant_filter && params.variant_filter !== 'all'
      ? { variant_filter: params.variant_filter }
      : {}),
    ...(params.discontinued_batch_id
      ? { discontinued_batch_id: params.discontinued_batch_id }
      : {}),
  });
}

/**
 * The list query a detail URL describes, in the exact shape `ProductsList`
 * passes - equal values, so the two keys hash equal.
 */
export function productsListParamsFromUrl(
  params: ListPagerParams,
): ProductsListParams {
  const f = params.filters;
  const variant = f.variant_filter;
  return {
    pageIndex: params.pageIndex,
    pageSize: params.pageSize,
    sorting: params.sorting,
    searchQuery: params.searchQuery,
    category_id: f.category_id,
    brand_id: f.brand_id,
    status: f.status ?? 'all',
    variant_filter:
      variant === 'base' || variant === 'variant' ? variant : 'all',
    discontinued_batch_id: f.discontinued_batch_id,
    // The deep link's brand slice IS the `brand_id` param when a batch is named.
    discontinued_brand_ids: f.discontinued_batch_id ? f.brand_id : undefined,
    advancedFilter:
      decodeAdvancedFilter<ListQueryFilterGroup>(f.advFilter) ?? undefined,
  };
}

/** The pager's two hooks into the products list, ready to spread into `ListPager`. */
export const productsPagerQuery = {
  listQueryKey: (params: ListPagerParams): QueryKey =>
    productsListQueryKey(productsListParamsFromUrl(params)),
  fetchPage: (params: ListPagerParams): Promise<ListPagerPage> =>
    fetchProductsPage(productsListParamsFromUrl(params)),
};
