/**
 * S3-01 - the other half of Back.
 *
 * Back hands the list its own query string back. Before this hook three lists
 * read it and fourteen ignored it, so Back landed on page 1 of an unfiltered
 * list. What is pinned here: the hook hands the caller everything the URL holds,
 * fires once per distinct URL, and stays out of the way of a list opened fresh.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, renderHook } from '@testing-library/react';

import { useListStateFromUrl } from './useListStateFromUrl';
import type { ListPagerParams } from './useListPager';

let search = '';

vi.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams(search),
}));

beforeEach(() => {
  search = '';
});

function renderWithUrl(url: string, options?: { enabled?: boolean }) {
  search = url;
  const apply = vi.fn<(state: ListPagerParams) => void>();
  const view = renderHook(({ enabled }) => useListStateFromUrl(apply, { enabled }), {
    initialProps: { enabled: options?.enabled ?? true },
  });
  return { apply, view };
}

describe('useListStateFromUrl', () => {
  it('S3-01: hands back the page, the sort, the search and every filter', () => {
    const { apply } = renderWithUrl(
      'page=3&limit=25&sort=name&dir=desc&query=ada&roleId=r1&status=active',
    );

    expect(apply).toHaveBeenCalledTimes(1);
    expect(apply.mock.calls[0][0]).toEqual({
      pageIndex: 2,
      pageSize: 25,
      sorting: [{ id: 'name', desc: true }],
      searchQuery: 'ada',
      filters: { roleId: 'r1', status: 'active' },
    });
  });

  it('S3-01: a list opened fresh keeps its own defaults', () => {
    const { apply } = renderWithUrl('');

    expect(apply).not.toHaveBeenCalled();
  });

  it('S3-01: fires once per URL, not once per render', () => {
    const { apply, view } = renderWithUrl('page=2&limit=50');

    view.rerender({ enabled: true });
    view.rerender({ enabled: true });

    expect(apply).toHaveBeenCalledTimes(1);
  });

  it('S3-01: a disabled list is left alone (the products hard-refresh clean slate)', () => {
    const { apply } = renderWithUrl('page=2&limit=50&category_id=c1', { enabled: false });

    expect(apply).not.toHaveBeenCalled();
  });

  /**
   * The list fetches from the state this hook restores. Applied in an effect, the
   * first commit would already have fetched page 1 of the unfiltered list, and the
   * restored page a moment later: two requests on every Back, one of them for a
   * page nobody asked for.
   */
  it('R11: the restored state is in place before the list can fetch, so it fetches once', () => {
    search = 'page=3&limit=25&query=ada';
    const fetches: string[] = [];

    function List() {
      const [state, setState] = React.useState<ListPagerParams>({
        pageIndex: 0,
        pageSize: 50,
        sorting: [],
        searchQuery: '',
        filters: {},
      });
      useListStateFromUrl((next) => setState(next));
      // Stands in for the list's `useQuery`, which subscribes on commit: a render
      // React throws away never issues a request.
      React.useEffect(() => {
        fetches.push(
          `page=${state.pageIndex + 1}&limit=${state.pageSize}&query=${state.searchQuery}`,
        );
      }, [state]);
      return null;
    }

    render(React.createElement(List));

    expect(fetches).toEqual(['page=3&limit=25&query=ada']);
  });
});
