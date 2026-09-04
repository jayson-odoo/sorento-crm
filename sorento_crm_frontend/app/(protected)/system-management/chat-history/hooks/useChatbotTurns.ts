'use client';

import { useMemo } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import {
  getChatbotTurns,
  indexTurnsByMessageId,
  retryChatbotTurn,
} from '../services/chatbotTurnService';
import type { ChatbotTurn } from '../types/chatbotTurn.types';

export const CHATBOT_TURNS_KEY = ['chatbot-turns'] as const;

/**
 * Every turn recorded for one contact, keyed by the respond message it answers.
 *
 * The transcript renders messages; the turn panel hangs off the INCOMING ones, so a map
 * by `message_id` is what the component actually wants and building it here keeps that
 * shape out of the render path.
 */
export function useChatbotTurns(
  contactId: string | null,
  /**
   * PHASE 1 ONLY. The mock turns carry invented `message_id`s that match nothing in the
   * real transcript, so they are stitched onto the first few incoming messages in order.
   * Phase 2 deletes this argument and the `stitched` branch below: the endpoint returns
   * turns whose `message_id` really is the one on the message.
   */
  incomingMessageIds: string[] = [],
) {
  const query = useQuery({
    queryKey: [...CHATBOT_TURNS_KEY, contactId],
    queryFn: () => getChatbotTurns({ contact_respond_id: contactId as string }),
    enabled: Boolean(contactId),
    staleTime: 15_000,
  });

  const byMessageId = useMemo(() => {
    const turns = query.data?.items ?? [];
    if (turns.length === 0) return new Map<string, ChatbotTurn>();

    const real = indexTurnsByMessageId(turns);
    const anyRealMatch = incomingMessageIds.some((id) => real.has(id));
    if (anyRealMatch || incomingMessageIds.length === 0) return real;

    // --- PHASE 1 STITCH (delete with the mock) -------------------------------
    const stitched = new Map<string, ChatbotTurn>();
    incomingMessageIds.forEach((id, index) => {
      const turn = turns[index];
      if (turn) stitched.set(id, turn);
    });
    return stitched;
    // -------------------------------------------------------------------------
  }, [query.data, incomingMessageIds]);

  return { ...query, byMessageId };
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
