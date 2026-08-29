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
import { renderHook } from '@testing-library/react';

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
});
