'use client';

import { useCallback, useRef, useState } from 'react';
import { cancelAgentAction, confirmAgentAction } from '../services/agentConsoleService';
import { postAutoTurn, type AutoBotTurn, type AutoTurnResponse } from '../services/autoConsoleService';
import type {
  AgentActionResponse,
  AgentPendingAction,
  AgentReplyMeta,
  AgentSteps,
  AgentTurnResponse,
  AutoRoute,
} from '../types/agentConsole.types';

const LAST_CONTACT_STORAGE_KEY = 'auto-console:last-contact';

interface StoredContact {
  id: string;
  label: string;
}

/** One message and the reply of whichever side the router chose. */
export interface AutoEntry {
  id: string;
  text: string;
  route: AutoRoute;
  reply: string;
  extraMessages: string[];
  meta: AgentReplyMeta | null;
  steps: AgentSteps | null;
  pendingAction: AgentPendingAction | null;
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

function newRunId(): string {
  const rand =
    typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `console-${rand}`;
}

function toEntry(text: string, result: AutoTurnResponse, id: string): AutoEntry {
  if (result.route.route === 'agent') {
    const turn = result.turn as AgentTurnResponse;
    return {
      id,
      text,
      route: result.route,
      reply: turn.reply_text,
      extraMessages: [],
      meta: { rounds: turn.rounds, tool_calls: turn.tool_calls, limit_hit: turn.limit_hit },
      steps: turn.steps && turn.steps.rounds > 0 ? turn.steps : null,
      pendingAction: turn.pending_action ?? null,
    };
  }
  const turn = result.turn as AutoBotTurn;
  return {
    id,
    text,
    route: result.route,
    reply: turn.reply_text,
    extraMessages: turn.send_messages ?? [],
    meta: null,
    steps: null,
    pendingAction: null,
  };
}

function messageOf(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

export function useAutoConsole() {
  const [contact, setContactState] = useState<StoredContact | null>(() => readStoredContact());
  const [entries, setEntries] = useState<AutoEntry[]>([]);
  const [pendingText, setPendingText] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  // The bot side's conversation, kept like the Bot tab keeps it; an agent reply leaves it alone.
  const [sessionVars, setSessionVars] = useState<Record<string, unknown> | null>({});
  const [runId, setRunId] = useState<string>(() => newRunId());
  const [outcomeByEntry, setOutcomeByEntry] = useState<Record<string, AgentActionResponse>>({});
  const [deciding, setDeciding] = useState(false);
  // A reply that lands after the contact was switched belongs to a thread that is gone.
  const generation = useRef(0);
  const contactId = contact?.id ?? null;

  const setContact = useCallback((id: string, label: string) => {
    generation.current += 1;
    setContactState({ id, label });
    setEntries([]);
    setPendingText(null);
    setNotice(null);
    setSessionVars({});
    setRunId(newRunId());
    setOutcomeByEntry({});
    try {
      window.localStorage.setItem(LAST_CONTACT_STORAGE_KEY, JSON.stringify({ id, label }));
    } catch {
      // Storage can be full or disabled; the tab still works.
    }
  }, []);

  const send = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!contactId || !trimmed || pendingText !== null) return;
      const mine = generation.current;
      setNotice(null);
      setPendingText(trimmed);
      try {
        const result = await postAutoTurn({
          contact_respond_id: contactId,
          text: trimmed,
          session_vars: sessionVars,
          run_id: runId,
        });
        if (mine !== generation.current) return;
        if (result.route.route === 'chat') {
          const next = (result.turn as AutoBotTurn).session_vars;
          if (next) setSessionVars(next);
        }
        setEntries((prev) => [...prev, toEntry(trimmed, result, `${prev.length}-${Date.now()}`)]);
      } catch (error) {
        if (mine === generation.current) setNotice(messageOf(error, 'The message could not be sent'));
      } finally {
        if (mine === generation.current) setPendingText(null);
      }
    },
    [contactId, pendingText, runId, sessionVars],
  );

  const decide = useCallback(
    async (actionId: string, entryId: string, decision: 'confirm' | 'cancel') => {
      if (!contactId) return;
      const mine = generation.current;
      setNotice(null);
      setDeciding(true);
      try {
        const result =
          decision === 'confirm'
            ? await confirmAgentAction(contactId, actionId)
            : await cancelAgentAction(contactId, actionId);
        if (mine === generation.current) setOutcomeByEntry((prev) => ({ ...prev, [entryId]: result }));
      } catch (error) {
        if (mine === generation.current) setNotice(messageOf(error, 'Failed to decide the changes'));
      } finally {
        setDeciding(false);
      }
    },
    [contactId],
  );

  return {
    contactId,
    contactLabel: contact?.label ?? '',
    setContact,
    entries,
    pendingText,
    notice,
    sending: pendingText !== null,
    send,
    deciding,
    outcomeByEntry,
    confirmAction: (actionId: string, entryId: string) => decide(actionId, entryId, 'confirm'),
    cancelAction: (actionId: string, entryId: string) => decide(actionId, entryId, 'cancel'),
  };
}
