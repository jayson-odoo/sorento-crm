'use client';

import { useMemo } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import {
  getChatbotTurns,
  getFailedChatbotContacts,
  indexTurnsByMessageId,
  retryChatbotTurn,
} from '../services/chatbotTurnService';
import type { FailedContactFilters } from '../types/chatbotTurn.types';

export const CHATBOT_TURNS_KEY = ['chatbot-turns'] as const;

/**
 * Every turn recorded for one contact, keyed by the respond message it answers.
 *
 * The transcript renders messages; the turn panel hangs off the INCOMING ones, so a map
 * by `message_id` is what the component actually wants and building it here keeps that
 * shape out of the render path.
 */
export function useChatbotTurns(contactId: string | null) {
  const query = useQuery({
    queryKey: [...CHATBOT_TURNS_KEY, contactId],
    // 200 is the endpoint's maximum page, and one page is the whole answer here: the
    // drawer renders ONE contact's transcript, and a conversation with more than 200 turns
    // is a different screen (the list, filtered to that contact). Deliberately not paged -
    // a "load more" inside a transcript would page the traces out of step with the
    // messages they hang off.
    queryFn: () => getChatbotTurns({ contact_respond_id: contactId as string, limit: 200 }),
    enabled: Boolean(contactId),
    staleTime: 15_000,
  });

  const byMessageId = useMemo(
    () => indexTurnsByMessageId(query.data?.items ?? []),
    [query.data],
  );

  // Whether Retry can work in this environment at all. It rides the list rather than a
  // route of its own: the screen needs it at the same moment it needs the turns.
  const retryUnavailableReason = query.data?.retry_available
    ? null
    : (query.data?.retry_unavailable_reason ?? null);

  return { ...query, byMessageId, retryUnavailableReason };
}

/**
 * AC-255. Which contacts have a failed turn in the range, for the LIST's own filter.
 *
 * `enabled` on purpose: the query only runs when the filter is on. Fetching it on every
 * page load would put an aggregate over the whole table behind a toggle most operators
 * never touch.
 */
export function useFailedChatbotContacts(filters: FailedContactFilters, enabled: boolean) {
  const query = useQuery({
    queryKey: [...CHATBOT_TURNS_KEY, 'failed-contacts', filters.from ?? null, filters.to ?? null],
    queryFn: () => getFailedChatbotContacts(filters),
    enabled,
    staleTime: 30_000,
  });

  const byContactId = useMemo(() => {
    const map = new Map<string, { last_failed_stage: string | null; count: number }>();
    for (const row of query.data?.items ?? []) {
      map.set(row.contact_respond_id, {
        last_failed_stage: row.last_failed_stage,
        count: row.count,
      });
    }
    return map;
  }, [query.data]);

  // The ids the LIST filters on, server-side. The map above is what the row badge reads;
  // this is what the query sends, and they must come from the same answer.
  const contactIds = useMemo(() => [...byContactId.keys()], [byContactId]);

  return { ...query, byContactId, contactIds };
}

/**
 * Manual retry. R4: this is the ONLY retry path - nothing retries a turn automatically,
 * and the endpoint refuses anything that is not `failed` with a 409.
 */
export function useRetryChatbotTurn() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (turnId: string) => retryChatbotTurn(turnId),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: CHATBOT_TURNS_KEY });
      toast.success(`Turn re-queued (attempt ${result.attempt}).`);
    },
    onError: (error) =>
      toast.error(error instanceof Error ? error.message : 'Could not retry this turn'),
  });
}
