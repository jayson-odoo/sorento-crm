/**
 * S3/B3 (reviewer, fix round 22 Sep 2026, `PLAN-oi-header-list-detail.md`).
 *
 * S3: `orderInquiryHeaderListParamsFromUrl` (the pager's own reconstruction of the
 * list's params from the detail URL) must default `state`/`sort`/`dir` the SAME way
 * `OrderInquiryHeadersList`'s own `params` memo does, or the pager's React Query key
 * differs from the list's own key on the very page a reader opens a detail from by
 * default (no `?state=`/`?sort=` in the URL) - a cache miss that fires a second,
 * redundant list request the moment `DetailActions`' pager mounts.
 *
 * B3: `orderInquiryHeadersPagerQuery.fetchPage` must surface the backend's own
 * `pagination.total` - `listOrderInquiryHeaders` (`orderInquiryService.ts`) is the one
 * function this pager and the list both call, so pinning it here is pinning both.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ListPagerParams } from '@/hooks/useListPager';

vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }));

const { apiFetch } = await import('@/lib/api');
const mockFetch = apiFetch as unknown as ReturnType<typeof vi.fn>;

import {
  orderInquiryHeadersListQueryKey,
  orderInquiryHeadersPagerQuery,
} from './useOrderInquiry';

function ok(body: unknown) {
  return { ok: true, json: async () => body } as unknown as Response;
}

beforeEach(() => mockFetch.mockReset());

describe('orderInquiryHeadersPagerQuery.listQueryKey (S3)', () => {
  it('a default detail URL (no state/sort/dir) builds the SAME key the list uses on first render', () => {
    const urlParams: ListPagerParams = {
      pageIndex: 0,
      pageSize: 25,
      sorting: [],
      searchQuery: '',
      filters: {},
    };
    // `OrderInquiryHeadersList`'s own `params` memo, first render (`DEFAULT_SORTING`,
    // `stateFilter`'s own initial value) - the exact object the list's own `useQuery`
    // is keyed on.
    const listsOwnKey = orderInquiryHeadersListQueryKey({
      state: 'outstanding',
      query: undefined,
      raised_by: undefined,
      agent: undefined,
      project: undefined,
      sort: 'raised_at',
      dir: 'asc',
      page: 1,
      limit: 25,
    });

    expect(orderInquiryHeadersPagerQuery.listQueryKey(urlParams)).toEqual(listsOwnKey);
  });

  it('a URL naming an explicit state/sort/project still builds the matching key', () => {
    const urlParams: ListPagerParams = {
      pageIndex: 1,
      pageSize: 25,
      sorting: [{ id: 'customer', desc: true }],
      searchQuery: 'CB6633',
      filters: { state: 'completed', agent: 'Sean', project: 'Tuju Residences' },
    };
    const listsOwnKey = orderInquiryHeadersListQueryKey({
      state: 'completed',
      query: 'CB6633',
      raised_by: undefined,
      agent: 'Sean',
      project: 'Tuju Residences',
      sort: 'customer',
      dir: 'desc',
      page: 2,
      limit: 25,
    });

    expect(orderInquiryHeadersPagerQuery.listQueryKey(urlParams)).toEqual(listsOwnKey);
  });
});

describe('orderInquiryHeadersPagerQuery.fetchPage (B3)', () => {
  it('surfaces the response pagination.total, not just the fetched page length', async () => {
    mockFetch.mockResolvedValue(
      ok({
        data: [{ id: 'oi-1' }],
        pagination: { total: 32, page: 1, limit: 25 },
      }),
    );

    const page = await orderInquiryHeadersPagerQuery.fetchPage({
      pageIndex: 0,
      pageSize: 25,
      sorting: [],
      searchQuery: '',
      filters: {},
    });

    expect(page.data).toHaveLength(1);
    expect((page as { total?: number }).total).toBe(32);
  });
});
