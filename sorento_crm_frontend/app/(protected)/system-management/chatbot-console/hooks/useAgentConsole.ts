'use client';

import { useCallback, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import {
  ActionRefusedError,
  AgentRefusedError,
  cancelAgentAction,
  confirmAgentAction,
  getAgentConversation,
  newAgentConversation,
  postAgentTurn,
} from '../services/agentConsoleService';
import type { AgentActionResponse, AgentReplyMeta } from '../types/agentConsole.types';

const LAST_CONTACT_STORAGE_KEY = 'agent-console:last-contact';

interface StoredContact {
  id: string;
  label: string;
}

function readStoredContact(): StoredContact | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(LAST_CONTACT_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<StoredContact>;
    if (typeof parsed.id === 'string' && typeof parsed.label === 'string') {
      return { id: parsed.id, label: parsed.label };
    }
  } catch {
    // A corrupt value is the same as absent.
  }
  return null;
}

export function useAgentConsole() {
  const queryClient = useQueryClient();
  const [contact, setContactState] = useState<StoredContact | null>(() => readStoredContact());
  // The text of the turn in flight, shown while the agent works.
  const [pendingText, setPendingText] = useState<string | null>(null);
  // Rounds and tool calls of the turns run in this visit, by turn id. History from the
  // server carries only text and reply.
  const [metaByTurn, setMetaByTurn] = useState<Record<string, AgentReplyMeta>>({});
  const [notice, setNotice] = useState<string | null>(null);
  // What Confirm / Cancel did, by the proposing turn's id, for the turns decided in this visit.
  const [outcomeByTurn, setOutcomeByTurn] = useState<Record<string, AgentActionResponse>>({});

  const contactId = contact?.id ?? null;
  const queryKey = ['agent-console', 'conversation', contactId];

  const conversation = useQuery({
    queryKey,
    queryFn: () => getAgentConversation(contactId as string),
    enabled: Boolean(contactId),
    retry: false,
  });
  // A contact the agent may not run for is told in words, not left as an empty thread.
  const loadRefusal =
    conversation.error instanceof AgentRefusedError ? conversation.error.message : null;

  const turn = useMutation({
    mutationFn: (text: string) => postAgentTurn(contactId as string, text),
    onMutate: (text) => {
      setNotice(null);
      setPendingText(text);
    },
    onSuccess: (result) => {
      setMetaByTurn((prev) => ({
        ...prev,
        [result.turn_id]: {
          rounds: result.rounds,
          tool_calls: result.tool_calls,
          limit_hit: result.limit_hit,
        },
      }));
    },
    onError: (error) => {
      if (error instanceof AgentRefusedError) {
        setNotice(error.message);
      } else {
        toast.error(error instanceof Error ? error.message : 'The agent could not run this turn');
      }
    },
    onSettled: async () => {
      await queryClient.invalidateQueries({ queryKey });
      setPendingText(null);
    },
  });

  const pendingAction = conversation.data?.pending_action ?? null;

  const decide = useMutation({
    mutationFn: ({ actionId, decision }: { actionId: string; turnId: string; decision: 'confirm' | 'cancel' }) =>
      decision === 'confirm'
        ? confirmAgentAction(contactId as string, actionId)
        : cancelAgentAction(contactId as string, actionId),
    onMutate: () => setNotice(null),
    onSuccess: (result, { turnId }) => {
      setOutcomeByTurn((prev) => ({ ...prev, [turnId]: result }));
    },
    onError: (error) => {
      if (error instanceof ActionRefusedError) {
        setNotice(error.message);
      } else {
        toast.error(error instanceof Error ? error.message : 'Failed to decide the changes');
      }
    },
    onSettled: async () => {
      await queryClient.invalidateQueries({ queryKey });
    },
  });

  const fresh = useMutation({
    mutationFn: () => newAgentConversation(contactId as string),
    onSuccess: async () => {
      setNotice(null);
      setMetaByTurn({});
      setOutcomeByTurn({});
      await queryClient.invalidateQueries({ queryKey });
    },
    onError: (error) => {
      if (error instanceof AgentRefusedError) {
        setNotice(error.message);
      } else {
        toast.error(error instanceof Error ? error.message : 'Failed to start a new conversation');
      }
    },
  });

  const setContact = useCallback((id: string, label: string) => {
    setContactState({ id, label });
    setNotice(null);
    setPendingText(null);
    setMetaByTurn({});
    setOutcomeByTurn({});
    try {
      window.localStorage.setItem(LAST_CONTACT_STORAGE_KEY, JSON.stringify({ id, label }));
    } catch {
      // Storage can be full or disabled; the tab still works.
    }
  }, []);

  const send = useCallback(
    (text: string) => {
      const trimmed = text.trim();
      if (!contactId || !trimmed || turn.isPending) return;
      turn.mutate(trimmed);
    },
    [contactId, turn],
  );

  return {
    contactId,
    contactLabel: contact?.label ?? '',
    setContact,
    turns: conversation.data?.turns ?? [],
    loading: Boolean(contactId) && conversation.isLoading,
    metaByTurn,
    pendingText,
    notice: notice ?? loadRefusal,
    sending: turn.isPending,
    send,
    startNew: () => fresh.mutate(),
    startingNew: fresh.isPending,
    pendingAction,
    outcomeByTurn,
    deciding: decide.isPending,
    confirmAction: (actionId: string, turnId: string) =>
      decide.mutate({ actionId, turnId, decision: 'confirm' }),
    cancelAction: (actionId: string, turnId: string) =>
      decide.mutate({ actionId, turnId, decision: 'cancel' }),
  };
}
