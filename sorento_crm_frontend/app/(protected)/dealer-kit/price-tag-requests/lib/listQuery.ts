/**
 * The list query the price tag request pager walks (D50, S3-03).
 *
 * The list writes its page, size, sort, search and status filter into the record
 * URL when a row is clicked; this parses that string back into the shape
 * `listPriceTagRequests` takes, so prev/next steps through the SAME searched,
 * sorted, filtered page the reader came from.
 *
 * The key is the pager's own React Query cache entry rather than a key shared
 * with the list: this list holds its rows in component state and never puts a
 * page in the query cache, so there is nothing to share and the pager fetches
 * the page once on arrival. Making the list a `useQuery` would remove that one
 * request; it is not worth rewriting a working list for.
 */

import type { QueryKey } from '@tanstack/react-query';
import type { ListPagerPage, ListPagerParams } from '@/hooks/useListPager';
import {
  listPriceTagRequests,
  type PriceTagRequestListParams,
} from '../../services/priceTagRequestService';

/** The list query a record URL describes, in the shape the list GET takes. */
export function priceTagRequestsListParamsFromUrl(
  params: ListPagerParams,
): PriceTagRequestListParams {
  const sort = params.sorting[0];
  return {
    page: params.pageIndex + 1,
    limit: params.pageSize,
    sort: sort?.id ?? 'created_at',
    dir: sort ? (sort.desc ? 'desc' : 'asc') : 'desc',
    query: params.searchQuery || undefined,
    // The list's own filter. Absent means every status, which is what the
    // list's `All statuses` option asks for.
    status: params.filters.status || undefined,
  };
}

/** The pager's two hooks into the price tag requests list. */
export const priceTagRequestsPagerQuery = {
  listQueryKey: (params: ListPagerParams): QueryKey => [
    'price-tag-requests',
    priceTagRequestsListParamsFromUrl(params),
  ],
  fetchPage: (params: ListPagerParams): Promise<ListPagerPage> =>
    listPriceTagRequests(priceTagRequestsListParamsFromUrl(params)),
};
