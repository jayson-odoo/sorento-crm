'use client';

import { useCallback } from 'react';
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import {
  CONVERSATION_INBOX_PAGE_SIZE,
  fetchContactMedia,
  getContactComments,
  getContactThreadPage,
  listConversations,
  replyToContact,
  searchContactThread,
  type ContactReplyInput,
  type ConversationInboxPage,
  type ConversationInboxTab,
} from '../services/conversationsInboxService';

/** How often the list re-reads itself while the page is open and focused. */
export const INBOX_REFRESH_MS = 30_000;
/**
 * How often the OPEN thread re-reads with NO live stream. Only ever one thread
 * at a time. This is the AC-K1 fallback lane.
 */
export const THREAD_POLL_MS = 10_000;
/**
 * The same poll while the live stream is connected - belt and braces behind the
 * pokes, not the mechanism.
 */
export const THREAD_POLL_LIVE_MS = 60_000;

export const conversationsInboxKey = (tab: ConversationInboxTab, q: string) =>
  ['conversations-inbox', tab, q] as const;

/**
 * The left list (AC-N1): one keyset page at a time, never the whole set.
 *
 * `useInfiniteQuery` because the cursor is opaque and the "Load more" row has
 * to send back exactly what the last page returned. The 30s interval stays as
 * it is: the live stream (slice S4.2) subscribes only to the OPEN thread, so a
 * poke refreshes this list for the selected contact and every other row still
 * relies on the interval. Subscribing the whole visible page would need up to
 * 30 contacts on a stream the backend caps at 25.
 */
export function useConversationsInbox(tab: ConversationInboxTab, q: string) {
  return useInfiniteQuery({
    queryKey: conversationsInboxKey(tab, q),
    queryFn: ({ pageParam }) =>
      listConversations({
        tab,
        q,
        cursor: pageParam as string | null,
        limit: CONVERSATION_INBOX_PAGE_SIZE,
      }),
    initialPageParam: null as string | null,
    getNextPageParam: (last: ConversationInboxPage) => last.next_cursor ?? undefined,
    refetchInterval: INBOX_REFRESH_MS,
    refetchIntervalInBackground: false,
    staleTime: 10_000,
    retry: 1,
  });
}

export const contactThreadKey = (contactRef: string | null) =>
  ['conversation-contact-thread', contactRef] as const;

/**
 * The newest window of a contact's thread, polled while the pane is open.
 *
 * `refetchIntervalMs` relaxes to `THREAD_POLL_LIVE_MS` once the live stream is
 * connected - the pokes carry the liveness then, and the poll is only there for
 * the seconds a reconnect takes.
 */
export function useContactThread(
  contactRef: string | null,
  options?: { refetchIntervalMs?: number },
) {
  return useQuery({
    queryKey: contactThreadKey(contactRef),
    queryFn: () => getContactThreadPage(contactRef as string, { limit: 50 }),
    enabled: !!contactRef,
    staleTime: 30_000,
    refetchInterval: options?.refetchIntervalMs ?? THREAD_POLL_MS,
    refetchIntervalInBackground: false,
    retry: 1,
  });
}

/**
 * The two loaders `useConversationThread` needs, memoised on the contact.
 * Same shape as `useSlaTrackingThreadLoaders`, contact-keyed instead of
 * ticket-keyed - the backend answers both from one service core.
 */
export function useContactThreadLoaders(contactRef: string | null) {
  const loadPage = useCallback(
    (params: { before?: string; after?: string; around?: string; limit?: number }) =>
      getContactThreadPage(contactRef ?? '', params),
    [contactRef],
  );
  const searchMessages = useCallback(
    (query: string) => searchContactThread(contactRef ?? '', query),
    [contactRef],
  );
  return { loadPage, searchMessages };
}

/** Chat-media byte loader for the inbox thread (AC-N4). */
export function useContactMediaProxy(contactRef: string | null) {
  return useCallback(
    (url: string) => fetchContactMedia(contactRef ?? '', url),
    [contactRef],
  );
}

export const contactCommentsKey = (contactRef: string | null) =>
  ['conversation-contact-comments', contactRef] as const;

/** Notes on this contact - both scopes (AC-N3). */
export function useContactComments(contactRef: string | null) {
  return useQuery({
    queryKey: contactCommentsKey(contactRef),
    queryFn: () => getContactComments(contactRef as string),
    enabled: !!contactRef,
    retry: 1,
  });
}

/**
 * Send to the contact from the inbox.
 *
 * `stamped_ticket_id` is surfaced by the caller, never enforced here: an
 * unstamped send still reached the contact, so failing or warning loudly would
 * be a lie about what happened.
 */
export function useReplyToContact(contactRef: string | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: ContactReplyInput) => replyToContact(contactRef as string, input),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: contactThreadKey(contactRef) });
      // The row's snippet and time have just changed.
      void queryClient.invalidateQueries({ queryKey: ['conversations-inbox'] });
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to send message'),
  });
}
