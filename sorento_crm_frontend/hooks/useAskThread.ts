'use client';

import { useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { AskThreadSource } from '@/components/stock-asks/AskConversationPanel';
import type {
  ConversationSearchMatch,
  ConversationThreadPage,
} from '@/components/common/conversation/useConversationThread';

/** The tail is the page read with no cursor; this is how many bubbles it holds. */
export const ASK_THREAD_TAIL_LIMIT = 50;
/** How often an open panel re-reads the tail (the ticket drawer's no-stream cadence). */
const TAIL_POLL_MS = 10_000;

export interface AskThreadService {
  getPage: (
    askId: string,
    params: { before?: string; after?: string; around?: string; limit?: number },
  ) => Promise<ConversationThreadPage>;
  search: (askId: string, query: string) => Promise<ConversationSearchMatch[]>;
}

/**
 * The opened ask's contact thread for `AskConversationPanel` (ASKS-UX item 3): the live tail
 * (polled while the panel is open) and the two loaders `useConversationThread` needs, memoised
 * on the ask id so the thread hook does not re-run its effects every render. One hook for both
 * mounts; each passes its own service pair (portal token vs CRM session), so the fetching stays
 * in the mount's service file. `queryPrefix` keeps the two caches apart.
 */
export function useAskThread(askId: string | null, service: AskThreadService, queryPrefix: string): AskThreadSource {
  const tail = useQuery({
    queryKey: [queryPrefix, 'ask-thread-tail', askId],
    queryFn: () => service.getPage(askId!, { limit: ASK_THREAD_TAIL_LIMIT }),
    enabled: Boolean(askId),
    staleTime: TAIL_POLL_MS,
    refetchInterval: TAIL_POLL_MS,
    refetchIntervalInBackground: false,
  });
  const loadPage = useCallback(
    (params: { before?: string; after?: string; around?: string; limit?: number }) =>
      service.getPage(askId ?? '', params),
    [askId, service],
  );
  const searchMessages = useCallback((query: string) => service.search(askId ?? '', query), [askId, service]);

  return {
    liveItems: tail.data?.items ?? [],
    loading: tail.isLoading,
    error: tail.isError ? (tail.error instanceof Error ? tail.error.message : 'Failed to load the conversation') : null,
    loadPage,
    searchMessages,
  };
}
