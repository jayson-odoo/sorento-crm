'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import { getChatbotTurns } from '../../chat-history/services/chatbotTurnService';
import { getRespondContactsOutbound } from '../../respond-contacts/services/respondContactOutboundService';
import { getConsolePromptVersions, postConsoleTurn } from '../services/chatbotConsoleService';
import {
  CONSOLE_GREETING_MESSAGES,
  type ChatbotConsoleMessage,
} from '../types/chatbotConsole.types';

const LAST_CONTACT_STORAGE_KEY = 'chatbot-console:last-contact';

interface StoredContact {
  id: string;
  label: string;
}

function newRunId(): string {
  const rand =
    typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `console-${rand}`;
}

function greetingMessages(): ChatbotConsoleMessage[] {
  return CONSOLE_GREETING_MESSAGES.map((text, index) => ({
    id: `greeting-${index}`,
    role: 'bot',
    text,
  }));
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
    // Ignored - a corrupt value is the same as absent.
  }
  return null;
}

function writeStoredContact(contact: StoredContact): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(LAST_CONTACT_STORAGE_KEY, JSON.stringify(contact));
  } catch {
    // Storage can be full or disabled; the console still works, it just forgets next visit.
  }
}

/** A contact row's display label, the same "no UUIDs in the UI" rule every other picker
 * follows - falls back to the phone, then to the id only when NEITHER name nor phone is on
 * file (a respond.io id is a short reference number, not an internal UUID). */
function contactLabel(row: { name: string | null; phone_number: string | null; respond_io_id: string | null }): string {
  return row.name || row.phone_number || row.respond_io_id || 'Unknown contact';
}

export function useChatbotConsole() {
  const [contactId, setContactIdState] = useState<string | null>(null);
  const [contactLabelState, setContactLabelState] = useState<string>('');
  const [promptVersionId, setPromptVersionId] = useState<string | null>(null);
  const [runId, setRunId] = useState<string>(() => newRunId());
  const [sessionVars, setSessionVars] = useState<Record<string, unknown> | null>({});
  const [messages, setMessages] = useState<ChatbotConsoleMessage[]>(() => greetingMessages());
  const [sending, setSending] = useState(false);
  const bootstrapped = useRef(false);

  const promptVersionsQuery = useQuery({
    queryKey: ['chatbot-console', 'prompt-versions'],
    queryFn: getConsolePromptVersions,
    staleTime: 60_000,
  });

  // Default contact: last used from localStorage, else the contact of the most recent
  // LIVE turn (excludes test/console turns by construction - `getChatbotTurns` defaults
  // `include_test=false`). Runs once.
  useEffect(() => {
    if (bootstrapped.current) return;
    bootstrapped.current = true;
    const stored = readStoredContact();
    if (stored) {
      setContactIdState(stored.id);
      setContactLabelState(stored.label);
      return;
    }
    (async () => {
      try {
        const turns = await getChatbotTurns({ limit: 1 });
        const latestId = turns.items[0]?.contact_respond_id;
        if (!latestId) return;
        const contacts = await getRespondContactsOutbound({
          pageIndex: 0,
          pageSize: 1,
          searchQuery: latestId,
        });
        const row = contacts.data[0];
        const label = row ? contactLabel(row) : latestId;
        setContactIdState(latestId);
        setContactLabelState(label);
      } catch {
        // No default resolvable (no prior turns, or the lookups failed) - the contact
        // picker simply opens empty and the operator picks one.
      }
    })();
  }, []);

  const resetThread = useCallback(() => {
    setRunId(newRunId());
    setSessionVars({});
    setMessages(greetingMessages());
  }, []);

  const setContact = useCallback(
    (id: string, label: string) => {
      setContactIdState(id);
      setContactLabelState(label);
      writeStoredContact({ id, label });
      // A different contact is a different borrowed session - carrying the old one
      // forward would silently mix two contacts' state in one reply.
      resetThread();
    },
    [resetThread],
  );

  const sendText = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || sending) return;
      if (!contactId) {
        toast.error('Pick a contact before sending a message.');
        return;
      }
      const userMessage: ChatbotConsoleMessage = {
        id: `user-${Date.now()}-${Math.random().toString(16).slice(2)}`,
        role: 'user',
        text: trimmed,
      };
      setMessages((prev) => [...prev, userMessage]);
      setSending(true);
      try {
        const result = await postConsoleTurn({
          contact_respond_id: contactId,
          text: trimmed,
          session_vars: sessionVars,
          prompt_version_id: promptVersionId,
          run_id: runId,
        });
        const bubbles: ChatbotConsoleMessage[] = [];
        const bodies = [
          ...(result.reply_text ? [result.reply_text] : []),
          ...result.send_messages,
        ];
        if (bodies.length === 0) bodies.push('(no reply)');
        bodies.forEach((body, index) => {
          bubbles.push({
            id: `bot-${result.turn_id ?? runId}-${index}`,
            role: 'bot',
            text: body,
            turnId: result.turn_id,
            branchKind: index === 0 ? result.branch_kind : undefined,
            quickReplies: index === bodies.length - 1 ? result.quick_replies : undefined,
          });
        });
        setMessages((prev) => [...prev, ...bubbles]);
        // Membership matters (see the service doc-comment): only overwrite when this
        // turn actually produced a patch. A turn that produced none (a failed lane)
        // must not be read as "the contact now remembers nothing".
        if (result.session_vars !== null) {
          setSessionVars(result.session_vars);
        }
        writeStoredContact({ id: contactId, label: contactLabelState });
      } catch (err) {
        toast.error(err instanceof Error ? err.message : 'Failed to run the turn');
      } finally {
        setSending(false);
      }
    },
    [contactId, contactLabelState, promptVersionId, runId, sending, sessionVars],
  );

  const sendQuickReply = useCallback((text: string) => sendText(text), [sendText]);

  return {
    contactId,
    contactLabel: contactLabelState,
    setContact,
    promptVersionId,
    setPromptVersionId,
    promptVersions: promptVersionsQuery.data ?? [],
    promptVersionsLoading: promptVersionsQuery.isLoading,
    messages,
    sending,
    sendText,
    sendQuickReply,
    reset: resetThread,
    runId,
  };
}
