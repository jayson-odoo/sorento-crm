/**
 * S3-03, S3-04, S3-05 - the page-scoped pager.
 *
 * The pager walks the list page the user came from, out of the React Query cache
 * the list already filled. What these tests pin down:
 *
 * - a step WITHIN the page costs no request (the whole point of sharing the key)
 * - a step ACROSS a page boundary fetches the neighbouring page once and lands on
 *   its near edge, with a URL that names the new page
 * - the absolute ends are disabled, and so is a step already in flight
 * - a boundary page that comes back empty kills that direction rather than
 *   swallowing the click
 * - a deep link fetches the page named in the URL, and the pager hides when the
 *   record is not on it
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { useListPager, type ListPagerParams, type ListPagerPage } from './useListPager';

const push = vi.fn();
const prefetch = vi.fn();
let search = '';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, prefetch }),
  useSearchParams: () => new URLSearchParams(search),
}));

const PAGE_SIZE = 3;
const TOTAL = 7;

/** Three pages: a1 a2 a3 | b1 b2 b3 | c1. */
const PAGES: Record<number, ListPagerPage> = {
  0: { data: [{ id: 'a1' }, { id: 'a2' }, { id: 'a3' }], pagination: { total: TOTAL } },
  1: { data: [{ id: 'b1' }, { id: 'b2' }, { id: 'b3' }], pagination: { total: TOTAL } },
  2: { data: [{ id: 'c1' }], pagination: { total: TOTAL } },
};

const listQueryKey = (params: ListPagerParams) => [
  'test-list',
  params.pageIndex,
  params.pageSize,
  params.sorting,
  params.searchQuery,
  params.filters,
];

const fetchPage = vi.fn(async (params: ListPagerParams) => PAGES[params.pageIndex]);

/** A page fetch the test resolves by hand, to inspect the pager mid-step. */
function deferredPage() {
  let release!: (page: ListPagerPage) => void;
  const promise = new Promise<ListPagerPage>((resolve) => {
    release = resolve;
  });
  fetchPage.mockImplementationOnce(() => promise);
  return release;
}

function paramsFor(pageIndex: number): ListPagerParams {
  return {
    pageIndex,
    pageSize: PAGE_SIZE,
    sorting: [],
    searchQuery: '',
    filters: {},
  };
}

let client: QueryClient;

function wrapper({ children }: { children: React.ReactNode }) {
  return React.createElement(QueryClientProvider, { client }, children);
}

/** The list page the user came from, already in the cache. */
function seed(pageIndex: number) {
  client.setQueryData(listQueryKey(paramsFor(pageIndex)), PAGES[pageIndex]);
}

function renderPager(currentId: string) {
  return renderHook(
    () =>
      useListPager({
        listQueryKey,
        fetchPage,
        detailPath: '/things',
        currentId,
      }),
    { wrapper },
  );
}

beforeEach(() => {
  push.mockReset();
  prefetch.mockReset();
  fetchPage.mockClear();
  search = 'page=1&limit=3';
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
});

describe('useListPager', () => {
  it('S3-03: reads the position from the list cache and issues no request', () => {
    seed(0);
    const { result } = renderPager('a2');

    expect(result.current.visible).toBe(true);
    expect(result.current.index).toBe(2);
    expect(result.current.total).toBe(3);
    expect(fetchPage).not.toHaveBeenCalled();
  });

  it('S3-03: a step within the page navigates without fetching', () => {
    seed(0);
    const { result } = renderPager('a2');

    act(() => result.current.goNext());

    expect(push).toHaveBeenCalledWith('/things/a3?page=1&limit=3&from=a3');
    expect(fetchPage).not.toHaveBeenCalled();
  });

  it('S3-04: next on the last row fetches the next page and lands on its first row', async () => {
    seed(0);
    const { result } = renderPager('a3');

    expect(result.current.hasNext).toBe(true);
    await act(async () => {
      result.current.goNext();
    });

    expect(fetchPage).toHaveBeenCalledTimes(1);
    expect(fetchPage.mock.calls[0][0].pageIndex).toBe(1);
    expect(push).toHaveBeenCalledWith('/things/b1?page=2&limit=3&from=b1');
  });

  it('S3-04: previous on the first row of page 2 lands on the last row of page 1', async () => {
    search = 'page=2&limit=3';
    seed(1);
    const { result } = renderPager('b1');

    expect(result.current.hasPrevious).toBe(true);
    await act(async () => {
      result.current.goPrevious();
    });

    expect(fetchPage).toHaveBeenCalledTimes(1);
    expect(fetchPage.mock.calls[0][0].pageIndex).toBe(0);
    expect(push).toHaveBeenCalledWith('/things/a3?page=1&limit=3&from=a3');
  });

  it('S3-04: previous is disabled on row 1 of page 1', () => {
    seed(0);
    const { result } = renderPager('a1');

    expect(result.current.hasPrevious).toBe(false);
    act(() => result.current.goPrevious());
    expect(push).not.toHaveBeenCalled();
  });

  it('S3-04: next is disabled on the last row of the last page', () => {
    search = 'page=3&limit=3';
    seed(2);
    const { result } = renderPager('c1');

    expect(result.current.hasNext).toBe(false);
    act(() => result.current.goNext());
    expect(push).not.toHaveBeenCalled();
  });

  it('S3-05: a deep link fetches the page named in the URL', async () => {
    search = 'page=2&limit=3';
    const { result } = renderPager('b2');

    await waitFor(() => expect(result.current.index).toBe(2));
    expect(fetchPage).toHaveBeenCalledTimes(1);
    expect(fetchPage.mock.calls[0][0].pageIndex).toBe(1);
    expect(result.current.visible).toBe(true);
  });

  it('S3-05: the pager hides when the record is not on the page', async () => {
    seed(0);
    const { result } = renderPager('not-on-this-page');

    await waitFor(() => expect(result.current.visible).toBe(false));
    expect(result.current.index).toBeNull();
    expect(result.current.hasPrevious).toBe(false);
    expect(result.current.hasNext).toBe(false);
  });

  it('D3: both chevrons are disabled while a boundary step is in flight', async () => {
    seed(0);
    const release = deferredPage();
    const { result } = renderPager('a3');

    expect(result.current.hasNext).toBe(true);
    expect(result.current.hasPrevious).toBe(true);

    act(() => result.current.goNext());

    // The page it lands on decides where the ends are, so until it answers
    // neither direction is walkable and neither click may start a second fetch.
    await waitFor(() => expect(result.current.hasNext).toBe(false));
    expect(result.current.hasPrevious).toBe(false);
    expect(result.current.isLoading).toBe(true);

    act(() => result.current.goNext());
    act(() => result.current.goPrevious());
    expect(fetchPage).toHaveBeenCalledTimes(1);

    await act(async () => {
      release(PAGES[1]);
    });
    expect(push).toHaveBeenCalledWith('/things/b1?page=2&limit=3&from=b1');
  });

  it('D3: a next page that comes back empty disables Next instead of doing nothing', async () => {
    seed(0);
    // `total` still promises a page 2; the fetch says there is nothing on it.
    fetchPage.mockImplementationOnce(async () => ({
      data: [],
      pagination: { total: TOTAL },
    }));
    const { result } = renderPager('a3');

    await act(async () => {
      result.current.goNext();
    });

    expect(push).not.toHaveBeenCalled();
    expect(result.current.hasNext).toBe(false);
    // The other direction is untouched: page 1 row 3 still steps back to row 2.
    expect(result.current.hasPrevious).toBe(true);
  });

  it('D3: a previous page that comes back empty disables Previous', async () => {
    search = 'page=2&limit=3';
    seed(1);
    fetchPage.mockImplementationOnce(async () => ({
      data: [],
      pagination: { total: TOTAL },
    }));
    const { result } = renderPager('b1');

    await act(async () => {
      result.current.goPrevious();
    });

    expect(push).not.toHaveBeenCalled();
    expect(result.current.hasPrevious).toBe(false);
    expect(result.current.hasNext).toBe(true);
  });

  it('M4-06: prefetches the prev and next hrefs as soon as the record mounts', async () => {
    seed(0);
    renderPager('a2');

    await waitFor(() => expect(prefetch).toHaveBeenCalledWith('/things/a1?page=1&limit=3&from=a1'));
    expect(prefetch).toHaveBeenCalledWith('/things/a3?page=1&limit=3&from=a3');
  });

  it('M4-06: prefetches each href only once, even across re-renders', async () => {
    seed(0);
    const { rerender } = renderPager('a2');

    await waitFor(() => expect(prefetch).toHaveBeenCalledTimes(2));
    rerender();
    rerender();

    expect(prefetch).toHaveBeenCalledTimes(2);
  });

  it('S3-04: a page fetched by a boundary step is cached, not fetched twice', async () => {
    seed(0);
    const { result } = renderPager('a3');

    await act(async () => {
      result.current.goNext();
    });
    expect(fetchPage).toHaveBeenCalledTimes(1);

    // The user is now on page 2: its rows came from that one fetch.
    search = 'page=2&limit=3';
    const second = renderPager('b1');
    expect(second.result.current.index).toBe(1);
    expect(fetchPage).toHaveBeenCalledTimes(1);
  });

  it('M5-07: every step href carries from=<the id it lands on>, not the id it started from', () => {
    seed(0);
    // Two different starting rows step to two different neighbours: `from`
    // has to name the LANDING row each time, not a fixed value.
    const forward = renderPager('a1');
    act(() => forward.result.current.goNext());
    expect(push).toHaveBeenLastCalledWith('/things/a2?page=1&limit=3&from=a2');

    const backward = renderPager('a3');
    act(() => backward.result.current.goPrevious());
    expect(push).toHaveBeenLastCalledWith('/things/a2?page=1&limit=3&from=a2');
  });
});
