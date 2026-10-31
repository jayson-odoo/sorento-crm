'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { extractTurnAttachments, type TurnAttachment } from '@/components/chatbot/TurnAttachments';
import { toast } from '@/lib/toast';
import { getChatbotTurns } from '../../chat-history/services/chatbotTurnService';
import { getRespondContactsOutbound } from '../../respond-contacts/services/respondContactOutboundService';
import {
  ActionRefusedError,
  AgentRefusedError,
  cancelAgentAction,
  confirmAgentAction,
  newAgentConversation,
  withdrawAgentStep,
} from '../services/agentConsoleService';
import {
  getConsoleMediaStatus,
  getConsolePromptVersions,
  getConsoleThread,
  postConsoleTurn,
} from '../services/chatbotConsoleService';
import type {
  AgentActionResponse,
  AgentPendingAction,
  AgentReplyMeta,
  AgentSteps,
} from '../types/agentConsole.types';
import {
  CONSOLE_GREETING_MESSAGES,
  type ChatbotConsoleMessage,
  type ConsoleMediaInput,
  type ConsoleQuote,
  type ConsolePromptVersion,
  type ConsoleThreadTurn,
  type ConsoleTurnResponse,
} from '../types/chatbotConsole.types';

const LAST_CONTACT_STORAGE_KEY = 'chatbot-console:last-contact';
// One run id per contact, so a reload finds the same bot turns; "New conversation" replaces it.
const RUN_STORAGE_PREFIX = 'chatbot-console:run:';
// How often the "still reading/transcribing" poll checks back, once a media turn's own
// synchronous wait already timed out server-side. Matches the plan's own "every 2 s".
const MEDIA_POLL_INTERVAL_MS = 2000;

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

function uniqueId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

/** The run this contact's console is in: the stored one, else a new one that is stored. */
function runIdFor(contactId: string, fresh = false): string {
  const key = `${RUN_STORAGE_PREFIX}${contactId}`;
  if (typeof window === 'undefined') return newRunId();
  try {
    const stored = window.localStorage.getItem(key);
    if (stored && !fresh) return stored;
    const created = newRunId();
    window.localStorage.setItem(key, created);
    return created;
  } catch {
    return newRunId(); // Storage is off: the run lasts this visit.
  }
}

const SESSION_STORAGE_PREFIX = 'chatbot-console:session:';

/** The bot's session as this contact's run last left it, so a reload does not forget a pending question. */
function readSession(contactId: string, runId: string): Record<string, unknown> {
  try {
    const raw = window.localStorage.getItem(`${SESSION_STORAGE_PREFIX}${contactId}`);
    const parsed = raw ? (JSON.parse(raw) as { run?: string; vars?: Record<string, unknown> }) : null;
    if (parsed && parsed.run === runId && parsed.vars && typeof parsed.vars === 'object') return parsed.vars;
  } catch {
    // A corrupt value is the same as absent.
  }
  return {};
}

function writeSession(contactId: string, runId: string, vars: Record<string, unknown>): void {
  try {
    window.localStorage.setItem(`${SESSION_STORAGE_PREFIX}${contactId}`, JSON.stringify({ run: runId, vars }));
  } catch {
    // Storage can be full or disabled; the session lasts this visit.
  }
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

/** Item 6: the version the console pins when the operator has not chosen one - the NEWEST
 * `full` body, never the newest overall and never the production label (which locally
 * sits on the compact lineage: the owner's turns ran the compact base twice unnoticed).
 * Null when no full version exists. */
export function defaultPromptVersionId(versions: ConsolePromptVersion[]): string | null {
  const full = versions.filter((v) => v.base === 'full');
  if (full.length === 0) return null;
  return full.reduce((best, v) => (v.version > best.version ? v : best)).id;
}

/** A contact row's display label, the same "no UUIDs in the UI" rule every other picker
 * follows - falls back to the phone, then to the id only when NEITHER name nor phone is on
 * file (a respond.io id is a short reference number, not an internal UUID). */
function contactLabel(row: { name: string | null; phone_number: string | null; respond_io_id: string | null }): string {
  return row.name || row.phone_number || row.respond_io_id || 'Unknown contact';
}

/** What a bubble needs of a turn: a `POST /console/turn` answer, or a `GET /console/thread` turn made to look like one. */
type BubbleSource = Pick<ConsoleTurnResponse, 'turn_id' | 'branch_kind' | 'reply_text' | 'prompt_version'> &
  Partial<Pick<ConsoleTurnResponse, 'send_messages' | 'quick_replies' | 'trace_summary' | 'actions' | 'route' | 'agent'>> & {
    /** The files a stored turn sent (a live turn carries them inside `actions`). */
    attachments?: TurnAttachment[];
  };

/** The agent bubble's chips: rounds, each tool and why it stopped. Null when there is nothing to show. */
function agentMetaOf(
  steps: AgentSteps | undefined,
  rounds: number | undefined,
  limitHit: AgentReplyMeta['limit_hit'] | undefined,
): AgentReplyMeta | null {
  const tools = (steps?.tool_calls ?? []).map((c) => ({ name: c.name, status: c.status }));
  const count = rounds ?? steps?.rounds ?? null;
  if (!count && tools.length === 0 && !limitHit) return null;
  return { rounds: count, tool_calls: tools, limit_hit: limitHit ?? null };
}

/** `reply_text` plus one bubble per `send_messages` entry, exactly the shape the plan
 * describes - shared between a plain text turn and the tail of a resolved media turn.
 * The turn's own `send_attachments` files (if any) ride the LAST bubble, the same
 * place `quickReplies` already rides. An agent turn is one bubble that also carries its
 * steps and the changes it proposed. */
function turnBubbles(result: BubbleSource, fallbackId: string, stored = false): ChatbotConsoleMessage[] {
  const sends = result.send_messages ?? [];
  const bodies = [...(result.reply_text ? [result.reply_text] : []), ...sends];
  // A stored turn without a reply is not "no reply": it is a turn with nothing to show.
  if (bodies.length === 0 && stored) return [];
  if (bodies.length === 0) bodies.push('(no reply)');
  const attachments = result.attachments ?? extractTurnAttachments(result.actions);
  const agent = result.agent ?? null;
  return bodies.map((body, index) => {
    const last = index === bodies.length - 1;
    return {
      id: `bot-${result.turn_id ?? fallbackId}-${index}`,
      role: 'bot' as const,
      text: body,
      turnId: result.turn_id,
      branchKind: index === 0 ? result.branch_kind : undefined,
      promptVersion: result.prompt_version ?? null,
      routingLine: index === 0 ? (result.trace_summary?.routing_line ?? null) : undefined,
      route: last ? (result.route ?? null) : undefined,
      quickReplies: last ? result.quick_replies : undefined,
      attachments: last && attachments.length > 0 ? attachments : undefined,
      ...(agent && last
        ? {
            agentSteps: agent.steps,
            agentActions: agent.actions ?? [],
            agentMeta: agentMetaOf(agent.steps, agent.rounds, agent.limit_hit),
          }
        : {}),
    };
  });
}

/** A stored thread turn as the bubbles it was shown as: the question, then the answer. */
function threadMessages(turns: ConsoleThreadTurn[]): ChatbotConsoleMessage[] {
  const messages = turns.flatMap((t) => [
    {
      id: `user-${t.turn_id}`,
      role: 'user' as const,
      text: t.user_text,
      messageId: t.side === 'chat' ? (t.message_id ?? null) : null,
    },
    ...turnBubbles(
      {
        turn_id: t.turn_id,
        branch_kind: t.branch_kind ?? null,
        reply_text: t.reply_text,
        send_messages: t.send_messages ?? [],
        attachments: t.attachments ?? [],
        prompt_version: t.prompt_version ?? null,
        route: t.route,
        agent:
          t.side === 'agent'
            ? {
                turn_id: t.turn_id,
                status: 'answered',
                limit_hit: t.limit_hit ?? null,
                pending_action: null,
                steps: t.steps,
                actions: t.actions,
              }
            : null,
      },
      t.turn_id,
      true,
    ),
  ]);
  return messages.map((m) => ({ ...m, fromRead: true }));
}

const isGreeting = (m: ChatbotConsoleMessage) => m.id.startsWith('greeting-');

/** Merge a read of the thread into what is shown. The FIRST read of a thread adds the turns the screen does
 * not know, before what was sent meanwhile (and replaces the greeting). Later reads only bring the agent
 * turns' steps and write cards up to date, so a turn from elsewhere never jumps into the middle and the
 * bubbles of this visit keep their chips and files. */
function applyThread(
  prev: ChatbotConsoleMessage[],
  turns: ConsoleThreadTurn[],
  firstRead: boolean,
): ChatbotConsoleMessage[] {
  const agentTurns = new Map(turns.filter((t) => t.side === 'agent').map((t) => [t.turn_id, t]));
  const patched = prev.map((m) => {
    const t = m.role === 'bot' && m.turnId ? agentTurns.get(m.turnId) : undefined;
    return t ? { ...m, agentSteps: t.steps, agentActions: t.actions } : m;
  });
  if (!firstRead) return patched;
  const known = new Set(prev.flatMap((m) => (m.turnId ? [m.turnId] : [])));
  const history = threadMessages(turns.filter((t) => !known.has(t.turn_id)));
  if (history.length === 0) return patched;
  return [...history, ...patched.filter((m) => !isGreeting(m))];
}

/** Add a turn's bubbles once: a read that landed first may already hold the same turn. */
function withTurn(
  prev: ChatbotConsoleMessage[],
  turnId: string | null,
  bubbles: ChatbotConsoleMessage[],
): ChatbotConsoleMessage[] {
  const rest = turnId ? prev.filter((m) => !m.fromRead || (m.turnId !== turnId && m.id !== `user-${turnId}`)) : prev;
  return [...rest, ...bubbles];
}

function mediaReadLine(kind: 'image' | 'audio', text: string): string {
  return kind === 'image' ? `Read from image: ${text}` : `Heard: ${text}`;
}

function mediaStatusLine(kind: 'image' | 'audio'): string {
  return kind === 'image' ? 'Reading image...' : 'Transcribing...';
}

export function useChatbotConsole() {
  const [contactId, setContactIdState] = useState<string | null>(null);
  const [contactLabelState, setContactLabelState] = useState<string>('');
  const [promptVersionId, setPromptVersionIdState] = useState<string | null>(null);
  // Item 6 (revised, PR #1273 retest): the operator's pick lives in React state ONLY for
  // this page session - never localStorage/sessionStorage/URL - so a reload always starts
  // from the newest full body again rather than replaying a stale pick from a prior visit.
  // This flag guards against re-defaulting over an explicit in-session pick (including an
  // explicit "live label" clear, id === null) once the versions list refetches.
  const promptChoiceApplied = useRef(false);
  const [runId, setRunId] = useState<string>(() => newRunId());
  const [sessionVars, setSessionVars] = useState<Record<string, unknown> | null>({});
  const [messages, setMessages] = useState<ChatbotConsoleMessage[]>(() => greetingMessages());
  const [sending, setSending] = useState(false);
  const [startingNew, setStartingNew] = useState(false);
  // The agent's waiting proposal, and what Confirm / Cancel did per proposing turn in this visit.
  const [pendingAction, setPendingAction] = useState<AgentPendingAction | null>(null);
  const [outcomeByTurn, setOutcomeByTurn] = useState<Record<string, AgentActionResponse>>({});
  // Why a proposal could no longer be decided or withdrawn, in words.
  const [notice, setNotice] = useState<string | null>(null);
  const bootstrapped = useRef(false);
  // A poll scheduled against a Reset/contact-switch mid-flight must not keep writing
  // bubbles into a thread that has moved on - bumped by `clearThread`,
  // and every poll tick checks it is still the generation that scheduled it.
  const generationRef = useRef(0);
  // The thread whose first read has been applied: only that read may add turns.
  const readKeyRef = useRef<string | null>(null);

  const promptVersionsQuery = useQuery({
    queryKey: ['chatbot-console', 'prompt-versions'],
    queryFn: getConsolePromptVersions,
    staleTime: 60_000,
  });

  const promptVersions = promptVersionsQuery.data;
  useEffect(() => {
    if (promptChoiceApplied.current || !promptVersions) return;
    promptChoiceApplied.current = true;
    setPromptVersionIdState(defaultPromptVersionId(promptVersions));
  }, [promptVersions]);

  const setPromptVersionId = useCallback((id: string | null) => {
    promptChoiceApplied.current = true;
    setPromptVersionIdState(id);
  }, []);

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
      const run = runIdFor(stored.id);
      setRunId(run);
      setSessionVars(readSession(stored.id, run));
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
        const run = runIdFor(latestId);
        setRunId(run);
        setSessionVars(readSession(latestId, run));
      } catch {
        // No default resolvable (no prior turns, or the lookups failed) - the contact
        // picker simply opens empty and the operator picks one.
      }
    })();
  }, []);

  /** Empty the thread for `nextRun`: no bubble, session, waiting proposal or decision carries over. */
  const clearThread = useCallback((nextRun: string, session: Record<string, unknown> = {}) => {
    generationRef.current += 1;
    setSending(false); // a reply still in flight belongs to the thread that was left
    readKeyRef.current = null; // the thread read again from here counts as a first read
    setRunId(nextRun);
    setSessionVars(session);
    setMessages(greetingMessages());
    setPendingAction(null);
    setOutcomeByTurn({});
    setNotice(null);
  }, []);

  const setContact = useCallback(
    (id: string, label: string) => {
      if (id === contactId) return; // the same contact keeps its thread
      setContactIdState(id);
      setContactLabelState(label);
      writeStoredContact({ id, label });
      // A different contact is a different borrowed session - carrying the old one
      // forward would silently mix two contacts' state in one reply. It comes back with
      // its own thread, read from the server.
      const run = runIdFor(id);
      clearThread(run, readSession(id, run));
    },
    [clearThread, contactId],
  );

  // The thread as the server holds it: read on load, on a contact switch and after a new run.
  const threadQuery = useQuery({
    queryKey: ['chatbot-console', 'thread', contactId, runId],
    queryFn: () => getConsoleThread(contactId as string, runId),
    enabled: Boolean(contactId),
    retry: false,
    gcTime: 0,
  });
  useEffect(() => {
    if (contactId && sessionVars) writeSession(contactId, runId, sessionVars);
  }, [contactId, runId, sessionVars]);

  const thread = threadQuery.data;
  const refetchThread = threadQuery.refetch;
  useEffect(() => {
    if (!thread) return;
    // A read from before the turn that made the waiting proposal does not know it: keep that one.
    setPendingAction((prev) =>
      thread.pending_action ?? (prev && !thread.turns.some((t) => t.turn_id === prev.turn_id) ? prev : null),
    );
    const key = `${contactId}|${runId}`;
    const firstRead = readKeyRef.current !== key;
    readKeyRef.current = key;
    setMessages((prev) => applyThread(prev, thread.turns, firstRead));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- a new read is the only trigger
  }, [thread]);

  /** A waiting change's window closed, or a card was decided: read the thread again so the cards stay true. */
  const refreshThread = useCallback(() => {
    if (contactId) void refetchThread();
  }, [contactId, refetchThread]);

  /** One "New conversation": a new agent conversation and a new run for the bot. */
  const startNew = useCallback(async () => {
    if (startingNew) return;
    setStartingNew(true);
    try {
      if (contactId) {
        try {
          await newAgentConversation(contactId);
        } catch (err) {
          // A contact the agent cannot run for has no agent side to start afresh: the bot side still does.
          // A busy agent is not that: nothing changed, so say so and keep the thread.
          if (!(err instanceof AgentRefusedError) || err.reason === 'agent_busy') {
            toast.error(err instanceof Error ? err.message : 'Failed to start a new conversation');
            return;
          }
        }
      }
      clearThread(contactId ? runIdFor(contactId, true) : newRunId());
    } finally {
      setStartingNew(false);
    }
  }, [clearThread, contactId, startingNew]);

  const decide = useMutation({
    mutationFn: ({ actionId, decision }: { actionId: string; turnId: string; decision: 'confirm' | 'cancel' }) =>
      decision === 'confirm'
        ? confirmAgentAction(contactId as string, actionId)
        : cancelAgentAction(contactId as string, actionId),
    onMutate: () => setNotice(null),
    onSuccess: (result, { turnId }) => {
      setOutcomeByTurn((prev) => ({ ...prev, [turnId]: result }));
      setPendingAction(null);
    },
    onError: (err) => {
      if (err instanceof ActionRefusedError) {
        // It can no longer be decided: the card goes, with the reason in words.
        setNotice(err.message);
        setPendingAction(null);
      } else {
        toast.error(err instanceof Error ? err.message : 'Failed to decide the changes');
      }
    },
    onSettled: refreshThread,
  });

  const withdraw = useMutation({
    mutationFn: ({ actionId, index }: { actionId: string; index: number }) =>
      withdrawAgentStep(contactId as string, actionId, index),
    onMutate: () => setNotice(null),
    onSuccess: (result) => toast.success(result.reply_text),
    onError: (err) =>
      err instanceof ActionRefusedError
        ? setNotice(err.message)
        : toast.error(err instanceof Error ? err.message : 'Failed to withdraw the change'),
    onSettled: refreshThread,
  });

  const sendText = useCallback(
    async (text: string, quote?: ConsoleQuote | null, options?: { forceAgent?: boolean }) => {
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
        ...(quote ? { quotedText: quote.text } : {}),
      };
      setMessages((prev) => [...prev, userMessage]);
      setSending(true);
      const generation = generationRef.current;
      try {
        const result = await postConsoleTurn({
          contact_respond_id: contactId,
          text: trimmed,
          session_vars: sessionVars,
          prompt_version_id: promptVersionId,
          run_id: runId,
          ...(quote ? { reply_to: { id: quote.id, text: quote.text, source: quote.source } } : {}),
          ...(options?.forceAgent ? { force_agent: true } : {}),
        });
        if (generationRef.current !== generation) {
          // The thread moved on: the reply is not for it, but the session it patched is this contact's.
          if (result.session_vars !== null) writeSession(contactId, runId, result.session_vars);
          return;
        }
        setMessages((prev) =>
          withTurn(
            prev.map((m) => (m.id === userMessage.id ? { ...m, messageId: result.message_id ?? null } : m)),
            result.turn_id,
            turnBubbles(result, uniqueId('local')),
          ),
        );
        if (result.agent) {
          if (result.agent.pending_action) setPendingAction(result.agent.pending_action);
          refreshThread();
        }
        // Membership matters (see the service doc-comment): only overwrite when this
        // turn actually produced a patch. A turn that produced none (a failed lane)
        // must not be read as "the contact now remembers nothing".
        if (result.session_vars !== null) {
          setSessionVars(result.session_vars);
        }
        writeStoredContact({ id: contactId, label: contactLabelState });
      } catch (err) {
        if (generationRef.current === generation) {
          toast.error(err instanceof Error ? err.message : 'Failed to run the turn');
        }
      } finally {
        if (generationRef.current === generation) setSending(false);
      }
    },
    [contactId, contactLabelState, promptVersionId, refreshThread, runId, sending, sessionVars],
  );

  // -------------------------------------------------------------------------------- //
  // Media (commit 2): image and voice through the real extractor.
  // -------------------------------------------------------------------------------- //

  /** Once a media turn resolves - synchronously, or after the poll below - run the
   * extracted text as an ordinary turn and append its reply bubbles. Caller already
   * pushed/updated the "Read from image: ..." / "Heard: ..." bubble. */
  const runMediaFollowUpTurn = useCallback(
    async (extractedText: string, caption: string, quote: ConsoleQuote | null) => {
      const text = (extractedText || caption).trim();
      if (!text || !contactId) return;
      const generation = generationRef.current;
      try {
        const result = await postConsoleTurn({
          contact_respond_id: contactId,
          text,
          session_vars: sessionVars,
          prompt_version_id: promptVersionId,
          run_id: runId,
          ...(quote ? { reply_to: quote } : {}),
        });
        if (generationRef.current !== generation) {
          if (result.session_vars !== null) writeSession(contactId, runId, result.session_vars);
          return;
        }
        setMessages((prev) => withTurn(prev, result.turn_id, turnBubbles(result, uniqueId('local'))));
        if (result.session_vars !== null) setSessionVars(result.session_vars);
        if (result.agent) {
          if (result.agent.pending_action) setPendingAction(result.agent.pending_action);
          refreshThread();
        }
      } catch (err) {
        toast.error(err instanceof Error ? err.message : 'Failed to run the turn');
      }
    },
    [contactId, promptVersionId, refreshThread, runId, sessionVars],
  );

  const pollMediaStatus = useCallback(
    (
      mediaId: string,
      statusBubbleId: string,
      media: ConsoleMediaInput,
      caption: string,
      quote: ConsoleQuote | null,
      generation: number,
    ) => {
      const tick = async () => {
        if (generationRef.current !== generation) return; // superseded by Reset/contact switch
        try {
          const status = await getConsoleMediaStatus(mediaId);
          if (generationRef.current !== generation) return;
          if (status.status === 'pending') {
            window.setTimeout(tick, MEDIA_POLL_INTERVAL_MS);
            return;
          }
          if (status.status === 'failed') {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === statusBubbleId
                  ? {
                      ...m,
                      text: status.error || 'Could not read the attachment.',
                      mediaStatus: 'failed',
                      mediaRetry: media,
                      mediaRetryQuote: quote,
                    }
                  : m,
              ),
            );
            setSending(false);
            return;
          }
          const text = status.text || '';
          setMessages((prev) =>
            prev.map((m) =>
              m.id === statusBubbleId ? { ...m, text: mediaReadLine(media.kind, text), mediaStatus: 'done' } : m,
            ),
          );
          await runMediaFollowUpTurn(text, caption, quote);
        } catch (err) {
          toast.error(err instanceof Error ? err.message : 'Failed to check the attachment status');
        } finally {
          if (generationRef.current === generation) setSending(false);
        }
      };
      window.setTimeout(tick, MEDIA_POLL_INTERVAL_MS);
    },
    [runMediaFollowUpTurn],
  );

  const sendMediaPayload = useCallback(
    async (media: ConsoleMediaInput, caption: string, quote: ConsoleQuote | null = null) => {
      if (!contactId) {
        toast.error('Pick a contact before sending a message.');
        return;
      }
      const generation = generationRef.current;
      setSending(true);
      try {
        const result = await postConsoleTurn({
          contact_respond_id: contactId,
          text: caption,
          session_vars: sessionVars,
          prompt_version_id: promptVersionId,
          run_id: runId,
          media,
          // A quoted voice note or image carries the quote like a text does.
          ...(quote ? { reply_to: quote } : {}),
        });
        if (generationRef.current !== generation) return;

        if (result.media_status === 'pending' && result.media_id) {
          const statusId = `media-status-${result.media_id}`;
          setMessages((prev) => [
            ...prev,
            { id: statusId, role: 'bot', text: mediaStatusLine(media.kind), mediaStatus: 'pending', mediaId: result.media_id },
          ]);
          pollMediaStatus(result.media_id, statusId, media, caption, quote, generation);
          return; // pollMediaStatus clears `sending` once it settles
        }

        if (result.media_status === 'failed') {
          setMessages((prev) => [
            ...prev,
            {
              id: `media-failed-${Date.now()}`,
              role: 'bot',
              text: result.media_error || 'Could not read the attachment.',
              mediaStatus: 'failed',
              mediaRetry: media,
              mediaRetryQuote: quote,
            },
          ]);
          // A caption fallback may still have produced a real turn (turn_id present).
          if (result.turn_id) {
            setMessages((prev) => withTurn(prev, result.turn_id, turnBubbles(result, uniqueId('local'))));
            if (result.session_vars !== null) setSessionVars(result.session_vars);
          }
          return;
        }

        // "done": resolved inline, within the request's own synchronous wait.
        if (result.media_text) {
          setMessages((prev) => [
            ...prev,
            {
              id: `media-read-${result.media_id ?? Date.now()}`,
              role: 'bot',
              text: mediaReadLine(media.kind, result.media_text as string),
              mediaStatus: 'done',
              mediaId: result.media_id,
            },
          ]);
        }
        setMessages((prev) => withTurn(prev, result.turn_id, turnBubbles(result, uniqueId('local'))));
        if (result.session_vars !== null) setSessionVars(result.session_vars);
        writeStoredContact({ id: contactId, label: contactLabelState });
      } catch (err) {
        toast.error(err instanceof Error ? err.message : 'Failed to send the attachment');
      } finally {
        if (generationRef.current === generation) setSending(false);
      }
    },
    [contactId, contactLabelState, pollMediaStatus, promptVersionId, runId, sessionVars],
  );

  const readFileAsBase64 = (file: File): Promise<string> =>
    new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        const result = String(reader.result || '');
        const comma = result.indexOf(',');
        resolve(comma >= 0 ? result.slice(comma + 1) : result);
      };
      reader.onerror = () => reject(reader.error ?? new Error('Could not read the file'));
      reader.readAsDataURL(file);
    });

  const sendMedia = useCallback(
    async (kind: 'image' | 'audio', file: File, caption: string, quote: ConsoleQuote | null = null) => {
      if (sending) return;
      if (!contactId) {
        toast.error('Pick a contact before sending a message.');
        return;
      }
      const objectUrl = URL.createObjectURL(file);
      setMessages((prev) => [
        ...prev,
        {
          id: `user-media-${Date.now()}`,
          role: 'user',
          text: caption.trim(),
          mediaKind: kind,
          mediaUrl: objectUrl,
          ...(quote ? { quotedText: quote.text } : {}),
        },
      ]);
      try {
        const content_base64 = await readFileAsBase64(file);
        const media: ConsoleMediaInput = {
          kind,
          filename: file.name || (kind === 'image' ? 'photo.jpg' : 'voice.webm'),
          mime: file.type || (kind === 'image' ? 'image/jpeg' : 'audio/webm'),
          content_base64,
        };
        await sendMediaPayload(media, caption.trim(), quote);
      } catch (err) {
        toast.error(err instanceof Error ? err.message : 'Failed to send the attachment');
      }
    },
    [contactId, sending, sendMediaPayload],
  );

  const retryMedia = useCallback(
    (media: ConsoleMediaInput, quote: ConsoleQuote | null = null) => {
      if (sending) return;
      void sendMediaPayload(media, '', quote);
    },
    [sending, sendMediaPayload],
  );

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
    sendMedia,
    retryMedia,
    threadLoading: Boolean(contactId) && threadQuery.isLoading,
    startNew,
    startingNew,
    runId,
    pendingAction,
    outcomeByTurn,
    notice,
    deciding: decide.isPending,
    confirmAction: (actionId: string, turnId: string) => decide.mutate({ actionId, turnId, decision: 'confirm' }),
    cancelAction: (actionId: string, turnId: string) => decide.mutate({ actionId, turnId, decision: 'cancel' }),
    withdrawing: withdraw.isPending,
    withdrawStep: (actionId: string, index: number) => withdraw.mutate({ actionId, index }),
    refreshThread,
  };
}
