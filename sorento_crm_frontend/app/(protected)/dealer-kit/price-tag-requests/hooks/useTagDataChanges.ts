/**
 * The live product-data diff behind an open request, polled (PLAN
 * price-tag-currency-token-extract-prompt.md section C).
 *
 * Measured 16 Sep on the local prod copy: the batched live resolve behind
 * `GET /{id}/data-changes` (`resolve_request_line_data`) costs 16-414 ms per
 * request. Polling one open page every 30s is under 1% of one worker, so
 * this is a plain react-query poll - no push channel, no listener - the same
 * shape `notifications-sheet.tsx`'s unread-count poll already uses.
 *
 * Replaces the designer's and the detail page's own `useState` + one-shot
 * `useEffect` (AC-C2/AC-C3): a product edited in another tab now reaches the
 * rail's red dot and the header's pill within 30s, or at once on refocus,
 * with no reload.
 */
import { useQuery, type UseQueryResult } from '@tanstack/react-query';

import { listTagDataChanges } from '../../services/priceTagDataService';
import type { TagDataChangeSet } from '@/lib/dealer-kit/product-data-changes';

const POLL_INTERVAL_MS = 30_000;

export function tagDataChangesKey(requestId: string): readonly unknown[] {
  return ['dealer-kit', 'price-tag-requests', requestId, 'data-changes'] as const;
}

/**
 * `enabled` is the caller's own call, not this hook's: a terminal request
 * (collected/rejected/void, or approved with a self print-by -
 * `isTerminalPriceTagStatus`) can decide nothing, so the caller passes
 * `enabled: false` and the query never fires at all - never even once.
 */
export function useTagDataChanges(
  requestId: string,
  options: { enabled: boolean },
): UseQueryResult<TagDataChangeSet[]> {
  return useQuery({
    queryKey: tagDataChangesKey(requestId),
    queryFn: () => listTagDataChanges(requestId),
    enabled: options.enabled,
    refetchInterval: POLL_INTERVAL_MS,
    // A hidden tab does not poll (AC-C1) - nobody is watching the red dot.
    refetchIntervalInBackground: false,
    // Refocusing the tab is the OTHER way a change shows up before 30s pass.
    refetchOnWindowFocus: true,
  });
}
