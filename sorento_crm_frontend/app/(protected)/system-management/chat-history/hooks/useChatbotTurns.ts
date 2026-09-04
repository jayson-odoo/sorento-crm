'use client';

import { useMemo } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import {
  getChatbotTurns,
  getFailedChatbotContacts,
  getRetryAvailability,
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
    queryFn: () => getChatbotTurns({ contact_respond_id: contactId as string, limit: 200 }),
    enabled: Boolean(contactId),
    staleTime: 15_000,
  });

  const byMessageId = useMemo(
    () => indexTurnsByMessageId(query.data?.items ?? []),
    [query.data],
  );

  return { ...query, byMessageId };
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

  return { ...query, byContactId };
}

/**
 * Whether Retry is wired in this environment (it is deliberately not, locally).
 *
 * Read once per screen rather than per turn: it is an environment fact, not a per-row
 * one, and the answer is the same for every button on the page.
 */
export function useRetryAvailability(enabled: boolean = true) {
  return useQuery({
    queryKey: [...CHATBOT_TURNS_KEY, 'retry-availability'],
    queryFn: getRetryAvailability,
    enabled,
    staleTime: 5 * 60_000,
  });
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
