import type { SortingState } from '@tanstack/react-table';
import { buildDetailSearch } from '@/lib/listNavQuery';

const LIST_STATE_KEYS = ['page', 'limit', 'sort', 'dir', 'query'];

/**
 * The list's own query string with its page, sort, search and every filter written in, so the
 * browser's Back button restores all of it. Params the list does not own (`from`, `tab`) are kept.
 */
export function listUrlSearch(
  currentSearch: string,
  state: {
    pageIndex: number;
    pageSize: number;
    sorting: SortingState;
    searchQuery: string;
    filters: Record<string, string | undefined>;
  },
): string {
  const next = new URLSearchParams(currentSearch);
  for (const key of [...LIST_STATE_KEYS, ...Object.keys(state.filters)]) next.delete(key);
  const written = new URLSearchParams(
    buildDetailSearch(
      { pageIndex: state.pageIndex, pageSize: state.pageSize, sorting: state.sorting, searchQuery: state.searchQuery },
      state.filters,
    ),
  );
  written.forEach((value, key) => next.set(key, value));
  return next.toString();
}
