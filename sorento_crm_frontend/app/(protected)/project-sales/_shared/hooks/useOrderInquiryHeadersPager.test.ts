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

const stepState = vi.hoisted(() => ({ search: '', push: vi.fn() }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: stepState.push, prefetch: vi.fn() }),
  useSearchParams: () => new URLSearchParams(stepState.search),
}));

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

describe('orderInquiryHeadersPagerQuery carries inquiry_no (AC-RF-27)', () => {
  it('the list call and the key both carry the detail URL inquiry_no', async () => {
    mockFetch.mockResolvedValue(ok({ data: [], pagination: { total: 0, page: 1, limit: 25 } }));
    const params: ListPagerParams = {
      pageIndex: 0,
      pageSize: 25,
      sorting: [],
      searchQuery: '',
      filters: { inquiry_no: 'OI-2610-001,OI-2610-002' },
    };
    await orderInquiryHeadersPagerQuery.fetchPage(params);
    const url = String(mockFetch.mock.calls[mockFetch.mock.calls.length - 1][0]);
    expect(new URLSearchParams(url.split('?')[1]).get('inquiry_no')).toBe('OI-2610-001,OI-2610-002');
    expect(orderInquiryHeadersPagerQuery.listQueryKey(params)).not.toEqual(
      orderInquiryHeadersPagerQuery.listQueryKey({ ...params, filters: {} }),
    );
  });
});

/**
 * AC-RF-80 / AC-RF-82: `?reserve=` on a detail page holds a list status OR a request id (the
 * one-OI email link). Only a list status may reach the headers API, and only a list status
 * may be carried on to the next OI.
 */
describe('the pager and ?reserve= (AC-RF-80, AC-RF-82)', () => {
  const reserveSent = async (reserve: string): Promise<string | null> => {
    mockFetch.mockClear();
    mockFetch.mockResolvedValue(ok({ data: [], pagination: { total: 0, page: 1, limit: 25 } }));
    await orderInquiryHeadersPagerQuery.fetchPage({
      pageIndex: 0,
      pageSize: 25,
      sorting: [],
      searchQuery: '',
      filters: { reserve },
    });
    const url = String(mockFetch.mock.calls[mockFetch.mock.calls.length - 1][0]);
    return new URLSearchParams(url.split('?')[1]).get('reserve');
  };

  it.each([
    ['a request id', '0b7f7a52-3c1e-4f0a-9d55-6f1c2a9e8b11'],
    ['the value requested', 'requested'],
  ])('AC-RF-80: %s is not sent to the headers list', async (_name, value) => {
    expect(await reserveSent(value)).toBeNull();
  });

  it.each(['parked', 'needs_reserve', 'notice_parked', 'reserved'])(
    'AC-RF-80: the list status %s is still sent',
    async (status) => {
      expect(await reserveSent(status)).toBe(status);
    },
  );

  it('AC-RF-80: the pager key for a request id equals the key without reserve', () => {
    const base: ListPagerParams = { pageIndex: 0, pageSize: 25, sorting: [], searchQuery: '', filters: {} };
    expect(
      orderInquiryHeadersPagerQuery.listQueryKey({ ...base, filters: { reserve: 'rr-1' } }),
    ).toEqual(orderInquiryHeadersPagerQuery.listQueryKey(base));
  });
});

describe('a prev/next step lands on this URL (AC-RF-82)', () => {
  async function stepUrl(search: string): Promise<URLSearchParams> {
    const React = await import('react');
    const { renderHook, act, waitFor } = await import('@testing-library/react');
    const { QueryClient, QueryClientProvider } = await import('@tanstack/react-query');
    const { useListPager } = await import('@/hooks/useListPager');
    stepState.search = search;
    stepState.push.mockClear();
    mockFetch.mockResolvedValue(
      ok({ data: [{ id: 'h-1' }, { id: 'h-2' }, { id: 'h-3' }], pagination: { total: 3, page: 1, limit: 25 } }),
    );
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const wrapper = ({ children }: { children: React.ReactNode }) =>
      React.createElement(QueryClientProvider, { client }, children);
    const { result } = renderHook(
      () =>
        useListPager({
          ...orderInquiryHeadersPagerQuery,
          detailPath: '/project-sales/order-inquiries',
          currentId: 'h-2',
        }),
      { wrapper },
    );
    await waitFor(() => expect(result.current.hasNext).toBe(true));
    act(() => result.current.goNext());
    await waitFor(() => expect(stepState.push).toHaveBeenCalled());
    const href = String(stepState.push.mock.calls[0][0]);
    expect(href).toContain('/project-sales/order-inquiries/h-3');
    return new URLSearchParams(href.split('?')[1] ?? '');
  }

  it('a request id is not carried on to the next OI', async () => {
    const query = await stepUrl('page=1&limit=25&reserve=0b7f7a52-3c1e-4f0a-9d55-6f1c2a9e8b11');
    expect(query.get('reserve')).toBeNull();
  });

  it('a list status stays, because the next OI is on that list', async () => {
    const query = await stepUrl('page=1&limit=25&reserve=needs_reserve');
    expect(query.get('reserve')).toBe('needs_reserve');
  });
});
