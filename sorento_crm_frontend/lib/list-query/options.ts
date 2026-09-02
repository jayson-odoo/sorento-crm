import { keepPreviousData, type UseQueryOptions } from '@tanstack/react-query';

/**
 * The one place every paginated list hook takes its React Query options from
 * (PLAN-ui-motion-round2 M4).
 *
 * `keepPreviousData` is what stops a page/sort/filter/search change from
 * unmounting the grid to a skeleton: the previous page's rows stay on screen,
 * dimmed via `DataGrid`'s `isPlaceholderData`, while the next page loads
 * behind them. Spread this into every `useQuery({...})` whose `queryKey`
 * carries page, size, sort, filter or search state:
 *
 *   useQuery({ ...LIST_QUERY_OPTIONS, queryKey, queryFn })
 *
 * `lib/list-query/options.inventory.test.ts` enumerates every such hook and
 * fails on a miss - it is the guardrail that keeps this the ONLY place list
 * latency is configured, rather than a per-hook repeat.
 */
export const LIST_QUERY_OPTIONS = {
  placeholderData: keepPreviousData,
} as const satisfies Partial<UseQueryOptions>;
