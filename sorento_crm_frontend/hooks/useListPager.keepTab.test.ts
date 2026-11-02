/**
 * NAV-KEEP-TAB: prev/next keeps the active tab (owner ruling 1 Nov 2026).
 *
 * The tab lives in the URL (`?tab=`, see `useUrlTab`). The pager must:
 * - copy it onto every step: in-page, across a page boundary, and the prefetched hrefs;
 * - keep the list state it already carries (page/sort/query/filters);
 * - NOT treat it as a list filter, or the list cache key misses and `tab=` is sent to the list GET.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { useListPager, type ListPagerParams, type ListPagerPage } from './useListPager';
import { parseDetailSearch } from '@/lib/listNavQuery';

const push = vi.fn();
const prefetch = vi.fn();
let search = '';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, prefetch }),
  useSearchParams: () => new URLSearchParams(search),
}));

const PAGES: Record<number, ListPagerPage> = {
  0: { data: [{ id: 'a1' }, { id: 'a2' }, { id: 'a3' }], pagination: { total: 4 } },
  1: { data: [{ id: 'b1' }], pagination: { total: 4 } },
};
const listQueryKey = (p: ListPagerParams) => ['keep-tab', p.pageIndex, p.pageSize, p.sorting, p.searchQuery, p.filters];
const fetchPage = vi.fn(async (p: ListPagerParams) => PAGES[p.pageIndex]);

let client: QueryClient;
const wrapper = ({ children }: { children: React.ReactNode }) =>
  React.createElement(QueryClientProvider, { client }, children);

function seed(pageIndex: number, filters: Record<string, string> = {}) {
  client.setQueryData(
    listQueryKey({ pageIndex, pageSize: 3, sorting: [{ id: 'created_at', desc: true }], searchQuery: 'pump', filters }),
    PAGES[pageIndex],
  );
}
const renderPager = (currentId: string) =>
  renderHook(() => useListPager({ listQueryKey, fetchPage, detailPath: '/things', currentId }), { wrapper });
const lastPush = () => new URL(push.mock.calls.at(-1)![0], 'http://h');

beforeEach(() => {
  push.mockReset();
  prefetch.mockReset();
  fetchPage.mockClear();
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
});

describe('parseDetailSearch', () => {
  it('reserves tab: it is the detail page state, not a list filter', () => {
    const parsed = parseDetailSearch(new URLSearchParams('page=2&status=open&tab=fulfilment'));
    expect(parsed.filters).toEqual({ status: 'open' });
  });
});

describe('useListPager keeps ?tab=', () => {
  it('reads the list cache with tab on the URL (tab is not part of the list key)', () => {
    search = 'page=1&limit=3&sort=created_at&dir=desc&query=pump&status=open&tab=fulfilment';
    seed(0, { status: 'open' });
    const { result } = renderPager('a2');
    expect(result.current.index).toBe(2);
    expect(fetchPage).not.toHaveBeenCalled();
  });

  it('next within the page keeps tab and the list filters/sort', () => {
    search = 'page=1&limit=3&sort=created_at&dir=desc&query=pump&status=open&tab=fulfilment';
    seed(0, { status: 'open' });
    const { result } = renderPager('a2');
    act(() => result.current.goNext());
    const url = lastPush();
    expect(url.pathname).toBe('/things/a3');
    expect(url.searchParams.get('tab')).toBe('fulfilment');
    expect(url.searchParams.get('status')).toBe('open');
    expect(url.searchParams.get('sort')).toBe('created_at');
    expect(url.searchParams.get('dir')).toBe('desc');
    expect(url.searchParams.get('query')).toBe('pump');
    expect(url.searchParams.get('from')).toBe('a3');
  });

  it('previous within the page keeps tab', () => {
    search = 'page=1&limit=3&sort=created_at&dir=desc&query=pump&tab=lines';
    seed(0);
    const { result } = renderPager('a2');
    act(() => result.current.goPrevious());
    expect(lastPush().pathname).toBe('/things/a1');
    expect(lastPush().searchParams.get('tab')).toBe('lines');
  });

  it('next across a page boundary keeps tab', async () => {
    search = 'page=1&limit=3&sort=created_at&dir=desc&query=pump&tab=lines';
    seed(0);
    const { result } = renderPager('a3');
    await act(async () => {
      result.current.goNext();
    });
    expect(lastPush().pathname).toBe('/things/b1');
    expect(lastPush().searchParams.get('page')).toBe('2');
    expect(lastPush().searchParams.get('tab')).toBe('lines');
  });

  it('the prefetched neighbour hrefs carry tab too (same URL the click pushes)', () => {
    search = 'page=1&limit=3&sort=created_at&dir=desc&query=pump&tab=lines';
    seed(0);
    renderPager('a2');
    const hrefs = prefetch.mock.calls.map((c) => new URL(c[0], 'http://h').searchParams.get('tab'));
    expect(hrefs.length).toBeGreaterThan(0);
    expect(hrefs.every((t) => t === 'lines')).toBe(true);
  });

  it('the default tab (no tab param) adds none', () => {
    search = 'page=1&limit=3&sort=created_at&dir=desc&query=pump';
    seed(0);
    const { result } = renderPager('a2');
    act(() => result.current.goNext());
    expect(lastPush().searchParams.has('tab')).toBe(false);
  });

  it('an edit-form pager (hrefFor) gets tab in its search too', () => {
    search = 'page=1&limit=3&sort=created_at&dir=desc&query=pump&tab=lines';
    seed(0);
    const { result } = renderHook(
      () =>
        useListPager({
          listQueryKey,
          fetchPage,
          detailPath: '/things',
          currentId: 'a2',
          hrefFor: (id, s) => `/things/${id}/edit?${s}`,
        }),
      { wrapper },
    );
    act(() => result.current.goNext());
    expect(lastPush().pathname).toBe('/things/a3/edit');
    expect(lastPush().searchParams.get('tab')).toBe('lines');
  });
});
