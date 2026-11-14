'use client';

import { useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import type { SortingState } from '@tanstack/react-table';
import { parseDetailSearch } from '@/lib/listNavQuery';
import { listUrlSearch } from '../../service-jobs/lib/listUrl';

/** The list state the address bar holds when a tab mounts (read once, so the first query is the right one). */
export function useInitialListState() {
  const searchParams = useSearchParams();
  const [initial] = useState(() => parseDetailSearch(new URLSearchParams(searchParams.toString())));
  return initial;
}

/** Write a tab's page, sort, search and filters back to its own address, so Back and a reload restore them. */
export function useWriteListUrl(
  state: { pageIndex: number; pageSize: number; sorting: SortingState; searchQuery: string },
  filters: Record<string, string | undefined>,
) {
  const filtersKey = JSON.stringify(filters);
  useEffect(() => {
    const next = listUrlSearch(window.location.search, { ...state, filters });
    if (next !== window.location.search.replace(/^\?/, '')) {
      window.history.replaceState(window.history.state, '', `${window.location.pathname}?${next}`);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.pageIndex, state.pageSize, state.sorting, state.searchQuery, filtersKey]);
}
