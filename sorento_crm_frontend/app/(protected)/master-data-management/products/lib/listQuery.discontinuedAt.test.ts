/**
 * `discontinued_from` / `discontinued_to` riding the detail URL into the pager
 * params (issue #1287, AC-FLT-5). The list and the detail page's pager MUST
 * build the same React Query key for the same page (see `listQuery.ts`'s own
 * top comment) - a filter the URL reader drops never reaches the fetch.
 */
import { describe, expect, it, vi } from 'vitest';
import type { ListPagerParams } from '@/hooks/useListPager';

const postListQuerySearch = vi.fn();
vi.mock('@/lib/list-query/listQueryService', () => ({
  postListQuerySearch: (...a: unknown[]) => postListQuerySearch(...a),
}));

import { productsListParamsFromUrl, productsListQueryKey, fetchProductsPage } from './listQuery';

const BASE: ListPagerParams = {
  pageIndex: 0,
  pageSize: 50,
  sorting: [],
  searchQuery: '',
  filters: {},
};

describe('products, discontinued date range rides the detail URL into the pager params', () => {
  it('reads both bounds off the URL filters and the query key differs from one without them', () => {
    const withRange = productsListParamsFromUrl({
      ...BASE,
      filters: { discontinued_from: '2026-09-01', discontinued_to: '2026-09-26' },
    });
    expect(withRange.discontinued_from).toBe('2026-09-01');
    expect(withRange.discontinued_to).toBe('2026-09-26');

    const withoutRange = productsListParamsFromUrl(BASE);

    expect(productsListQueryKey(withRange)).not.toEqual(
      productsListQueryKey(withoutRange),
    );
  });

  it('advanced-filter search carries the discontinued range', async () => {
    postListQuerySearch.mockReset();
    postListQuerySearch.mockResolvedValue({
      data: [],
      pagination: { total: 0, page: 1, limit: 50 },
      empty: true,
    });

    await fetchProductsPage({
      pageIndex: 0,
      pageSize: 50,
      sorting: [],
      searchQuery: '',
      advancedFilter: { op: 'and', children: [{ field_key: 'is_active', op: 'eq', value: true }] },
      discontinued_from: '2026-09-01',
      discontinued_to: '2026-09-26',
    });

    expect(postListQuerySearch).toHaveBeenCalledTimes(1);
    const body = postListQuerySearch.mock.calls[0][0] as Record<string, unknown>;
    expect(body.discontinued_from).toBe('2026-09-01');
    expect(body.discontinued_to).toBe('2026-09-26');
  });
});
