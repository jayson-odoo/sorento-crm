'use client';

import { useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import type {
  ConversationSearchMatch,
  ConversationThreadLoaders,
  ConversationThreadPage,
} from '@/components/common/conversation/useConversationThread';
import type { RespondMessageRenderable } from '@/lib/respondIoChatRender';

/**
 * What the mount hands `AskConversationPanel` about the ask's contact thread (ASKS-UX item 3):
 * the live tail it keeps polling, plus the two loaders `useConversationThread` needs for
 * scroll-back, search and the jump to the anchor. The mount owns the fetching (portal token or
 * CRM session); the panel owns nothing about it.
 */
export interface AskThreadSource {
  liveItems: RespondMessageRenderable[];
  /** True until the tail has been read once. */
  loading: boolean;
  /** The FIRST tail read failed (nothing to show); a failed poll on a loaded tail is not one. */
  error: string | null;
  loadPage: ConversationThreadLoaders['loadPage'];
  searchMessages: ConversationThreadLoaders['searchMessages'];
}

/** One identity while there is no tail, so the thread hook's memos do not recompute per render. */
const NO_ITEMS: RespondMessageRenderable[] = [];

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
    retry: 1,
  });
  const loadPage = useCallback(
    (params: { before?: string; after?: string; around?: string; limit?: number }) =>
      service.getPage(askId ?? '', params),
    [askId, service],
  );
  const searchMessages = useCallback((query: string) => service.search(askId ?? '', query), [askId, service]);

  return {
    liveItems: tail.data?.items ?? NO_ITEMS,
    loading: tail.isLoading,
    // A failed poll with a tail already on screen must not blank the thread (and lose the
    // reader's place): only the read that left nothing to show is an error here.
    error:
      tail.isError && !tail.data
        ? tail.error instanceof Error
          ? tail.error.message
          : 'Failed to load the conversation'
        : null,
    loadPage,
    searchMessages,
  };
}
