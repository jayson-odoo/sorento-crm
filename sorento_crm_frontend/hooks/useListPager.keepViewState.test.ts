/**
 * OI-UX-FILTER-SNAPSHOT (owner, 3 Nov): a detail page's own grid view state (the OI's lines
 * search, State filter, sort) rides in the URL under `view_*` keys. The pager must:
 * - carry every `view_*` key onto each step (in-page, across a page boundary, prefetch);
 * - NOT read them as list filters (the list cache key would miss and `view_*` hit the list GET).
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
const listQueryKey = (p: ListPagerParams) => ['keep-view', p.pageIndex, p.pageSize, p.sorting, p.searchQuery, p.filters];
const fetchPage = vi.fn(async (p: ListPagerParams) => PAGES[p.pageIndex]);

let client: QueryClient;
const wrapper = ({ children }: { children: React.ReactNode }) =>
  React.createElement(QueryClientProvider, { client }, children);

function seed(pageIndex: number, filters: Record<string, string> = {}) {
  client.setQueryData(
    listQueryKey({ pageIndex, pageSize: 3, sorting: [], searchQuery: '', filters }),
    PAGES[pageIndex],
  );
}
const renderPager = (currentId: string) =>
  renderHook(() => useListPager({ listQueryKey, fetchPage, detailPath: '/things', currentId }), { wrapper });
const lastPush = () => new URL(push.mock.calls.at(-1)![0], 'http://h');

const VIEW = 'view_q=pump&view_state=reserve%3Arequested%2Cplaced&view_sort=item_code%3Adesc';

beforeEach(() => {
  push.mockReset();
  prefetch.mockReset();
  fetchPage.mockClear();
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
});

describe('parseDetailSearch', () => {
  it('keeps view_* keys out of the list filters', () => {
    const parsed = parseDetailSearch(new URLSearchParams(`page=1&status=open&${VIEW}`));
    expect(parsed.filters).toEqual({ status: 'open' });
  });
});

describe('useListPager keeps view_* state', () => {
  it('reads the list cache with view_* on the URL', () => {
    search = `page=1&limit=3&status=open&${VIEW}`;
    seed(0, { status: 'open' });
    const { result } = renderPager('a2');
    expect(result.current.index).toBe(2);
    expect(fetchPage).not.toHaveBeenCalled();
  });

  it('next within the page carries every view_* key verbatim', () => {
    search = `page=1&limit=3&status=open&tab=lines&${VIEW}`;
    seed(0, { status: 'open' });
    const { result } = renderPager('a2');
    act(() => result.current.goNext());
    const url = lastPush();
    expect(url.pathname).toBe('/things/a3');
    expect(url.searchParams.get('view_q')).toBe('pump');
    expect(url.searchParams.get('view_state')).toBe('reserve:requested,placed');
    expect(url.searchParams.get('view_sort')).toBe('item_code:desc');
    expect(url.searchParams.get('status')).toBe('open');
    expect(url.searchParams.get('tab')).toBe('lines');
  });

  it('previous carries them too', () => {
    search = `page=1&limit=3&${VIEW}`;
    seed(0);
    const { result } = renderPager('a2');
    act(() => result.current.goPrevious());
    expect(lastPush().pathname).toBe('/things/a1');
    expect(lastPush().searchParams.get('view_state')).toBe('reserve:requested,placed');
  });

  it('a step across a page boundary carries them', async () => {
    search = `page=1&limit=3&${VIEW}`;
    seed(0);
    const { result } = renderPager('a3');
    await act(async () => {
      result.current.goNext();
    });
    expect(lastPush().pathname).toBe('/things/b1');
    expect(lastPush().searchParams.get('view_q')).toBe('pump');
  });

  it('the prefetched hrefs carry them (same URL the click pushes)', () => {
    search = `page=1&limit=3&${VIEW}`;
    seed(0);
    renderPager('a2');
    const qs = prefetch.mock.calls.map((c) => new URL(c[0], 'http://h').searchParams.get('view_q'));
    expect(qs.length).toBeGreaterThan(0);
    expect(qs.every((q) => q === 'pump')).toBe(true);
  });
});
