'use client';

import Link from 'next/link';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  Bot,
  ChevronsRight,
  GitBranch,
  History,
  Loader2,
  Plus,
  SendHorizonal,
  Sparkles,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  fetchAIAssistantGreeting,
  listAIAssistantConversations,
  loadConversation,
  sendAIAssistantMessage,
  type AIAssistantConversationSummary,
  type AIAssistantMessage,
} from '@/lib/aiAssistantChatApi';
import { getPageSnapshot } from '@/lib/aiPageSnapshot';
import { useHasPermission } from '@/hooks/usePermissions';

const SIZE_STORAGE_KEY = 'sorento.ai.bubbleSize';
const OPEN_STORAGE_KEY = 'sorento.ai.bubbleOpen';
const DEFAULT_SIZE = { width: 384, height: 600 };
const MIN_WIDTH = 320;
const MIN_HEIGHT = 400;

interface BubbleSize {
  width: number;
  height: number;
}

function clampSize(size: BubbleSize): BubbleSize {
  if (typeof window === 'undefined') {
    return {
      width: Math.max(size.width, MIN_WIDTH),
      height: Math.max(size.height, MIN_HEIGHT),
    };
  }
  const maxW = Math.max(MIN_WIDTH, Math.floor(window.innerWidth * 0.5));
  const maxH = Math.max(MIN_HEIGHT, Math.floor(window.innerHeight * 0.8));
  return {
    width: Math.min(Math.max(size.width, MIN_WIDTH), maxW),
    height: Math.min(Math.max(size.height, MIN_HEIGHT), maxH),
  };
}

function formatRelativeTime(iso: string): string {
  try {
    const then = new Date(iso).getTime();
    if (!Number.isFinite(then)) return '';
    const diffSec = Math.max(0, Math.floor((Date.now() - then) / 1000));
    if (diffSec < 60) return `${diffSec}s ago`;
    const diffMin = Math.floor(diffSec / 60);
    if (diffMin < 60) return `${diffMin}m ago`;
    const diffHr = Math.floor(diffMin / 60);
    if (diffHr < 24) return `${diffHr}h ago`;
    const diffDay = Math.floor(diffHr / 24);
    if (diffDay < 30) return `${diffDay}d ago`;
    const diffMo = Math.floor(diffDay / 30);
    if (diffMo < 12) return `${diffMo}mo ago`;
    return `${Math.floor(diffMo / 12)}y ago`;
  } catch {
    return '';
  }
}

export default function AIAssistantBubble() {
  const canUseAIAssistant = useHasPermission('system.ai_assistant_chat.use');
  // Admins can jump from any assistant message to its per-turn trace (M2).
  const canViewTrace = useHasPermission('system.ai_assistant_settings.view');
  const [open, setOpen] = useState(false);
  const [conversationId, setConversationId] = useState<string | undefined>(undefined);
  const [messages, setMessages] = useState<AIAssistantMessage[]>([]);
  const [input, setInput] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [bubbleSize, setBubbleSize] = useState<BubbleSize>(DEFAULT_SIZE);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyItems, setHistoryItems] = useState<AIAssistantConversationSummary[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [historySearch, setHistorySearch] = useState('');
  const [greeting, setGreeting] = useState<string>('Hi, how can I help you?');
  const [greetingSuggestions, setGreetingSuggestions] = useState<string[]>([]);
  const greetingFetchedRef = useRef(false);
  const handleRef = useRef<HTMLButtonElement | null>(null);
  const panelRef = useRef<HTMLDivElement | null>(null);
  const focusAfterToggleRef = useRef<'handle' | 'panel' | null>(null);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const messageRefs = useRef<Map<string, HTMLDivElement>>(new Map());
  const [highlightedMessageId, setHighlightedMessageId] = useState<string | null>(null);
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const deepLinkConvId = searchParams?.get('ai_conversation') ?? null;
  const deepLinkMsgId = searchParams?.get('ai_message') ?? null;
  const handledDeepLinkRef = useRef<string | null>(null);
  const canSend = input.trim().length > 0 && !isSending;

  const sortedMessages = useMemo(
    () => [...messages].sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()),
    [messages],
  );

  const lastMessage = sortedMessages.length > 0 ? sortedMessages[sortedMessages.length - 1] : null;
  const suggestions =
    lastMessage && lastMessage.role === 'assistant'
      ? (lastMessage.metadata_json?.suggestions || []).slice(0, 5)
      : [];

  // Collapsed is the default: a first-time user gets the slim edge handle, not a
  // panel over the page. A user who left the panel expanded gets it back, across
  // navigations and reloads. Read in an effect, not in the useState initializer,
  // because the server renders this component too.
  useEffect(() => {
    if (typeof window === 'undefined') return;
    try {
      if (window.localStorage.getItem(OPEN_STORAGE_KEY) === '1') setOpen(true);
    } catch {
      // ignore unreadable storage
    }
  }, []);

  const setOpenPersisted = useCallback((value: boolean) => {
    // The handle and the panel swap places, so the element that was focused
    // unmounts - hand focus to whichever replaced it or the keyboard user lands
    // back on the document body.
    focusAfterToggleRef.current = value ? 'panel' : 'handle';
    setOpen(value);
    try {
      window.localStorage.setItem(OPEN_STORAGE_KEY, value ? '1' : '0');
    } catch {
      // ignore unwritable storage
    }
  }, []);

  useEffect(() => {
    if (!focusAfterToggleRef.current) return;
    if (focusAfterToggleRef.current === 'panel' && open) panelRef.current?.focus?.();
    if (focusAfterToggleRef.current === 'handle' && !open) handleRef.current?.focus?.();
    focusAfterToggleRef.current = null;
  }, [open]);

  // Load persisted size on mount
  useEffect(() => {
    if (typeof window === 'undefined') return;
    try {
      const raw = window.localStorage.getItem(SIZE_STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw) as Partial<BubbleSize>;
        if (
          parsed &&
          typeof parsed.width === 'number' &&
          typeof parsed.height === 'number'
        ) {
          setBubbleSize(clampSize({ width: parsed.width, height: parsed.height }));
          return;
        }
      }
    } catch {
      // ignore parse errors
    }
    setBubbleSize(clampSize(DEFAULT_SIZE));
  }, []);

  // Re-clamp on viewport resize
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const onResize = () => setBubbleSize((prev) => clampSize(prev));
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [sortedMessages.length, isSending]);

  // Greeting fetch on first open with no messages and no conversation loaded.
  useEffect(() => {
    if (!open) return;
    if (greetingFetchedRef.current) return;
    if (messages.length > 0) return;
    if (conversationId) return;
    greetingFetchedRef.current = true;
    let cancelled = false;
    (async () => {
      try {
        const data = await fetchAIAssistantGreeting();
        if (cancelled) return;
        setGreeting(data.greeting || 'Hi, how can I help you?');
        setGreetingSuggestions(Array.isArray(data.suggestions) ? data.suggestions.slice(0, 5) : []);
      } catch {
        // Silent fail — fallback strings already set.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open, messages.length, conversationId]);

  // Reset greeting-fetched flag when user clicks "New" (clears messages + conversation).
  useEffect(() => {
    if (!conversationId && messages.length === 0) {
      greetingFetchedRef.current = false;
    }
  }, [conversationId, messages.length]);

  // Debounced history fetch
  useEffect(() => {
    if (!open || !historyOpen) return;
    let cancelled = false;
    setHistoryLoading(true);
    setHistoryError(null);
    const t = window.setTimeout(async () => {
      try {
        const res = await listAIAssistantConversations({ q: historySearch || undefined, limit: 100 });
        if (!cancelled) setHistoryItems(res.items || []);
      } catch (err) {
        if (!cancelled) setHistoryError((err as Error)?.message || 'Failed to load conversations');
      } finally {
        if (!cancelled) setHistoryLoading(false);
      }
    }, 300);
    return () => {
      cancelled = true;
      window.clearTimeout(t);
    };
  }, [open, historyOpen, historySearch]);

  const persistSize = useCallback((size: BubbleSize) => {
    try {
      window.localStorage.setItem(SIZE_STORAGE_KEY, JSON.stringify(size));
    } catch {
      // ignore
    }
  }, []);

  const startResize = useCallback(
    (axis: 'top' | 'left' | 'corner') => (e: React.MouseEvent) => {
      e.preventDefault();
      e.stopPropagation();
      const startX = e.clientX;
      const startY = e.clientY;
      const startW = bubbleSize.width;
      const startH = bubbleSize.height;
      const prevUserSelect = document.body.style.userSelect;
      document.body.style.userSelect = 'none';

      const onMove = (ev: MouseEvent) => {
        // Dragging up (decreasing Y) increases height; left (decreasing X) increases width.
        const dx = startX - ev.clientX;
        const dy = startY - ev.clientY;
        let nextW = startW;
        let nextH = startH;
        if (axis === 'left' || axis === 'corner') nextW = startW + dx;
        if (axis === 'top' || axis === 'corner') nextH = startH + dy;
        setBubbleSize(clampSize({ width: nextW, height: nextH }));
      };
      const onUp = () => {
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup', onUp);
        document.body.style.userSelect = prevUserSelect;
        setBubbleSize((prev) => {
          const clamped = clampSize(prev);
          persistSize(clamped);
          return clamped;
        });
      };
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
    },
    [bubbleSize.height, bubbleSize.width, persistSize],
  );

  const sendText = useCallback(
    async (text: string, confirmAction?: 'confirm' | 'cancel') => {
      const trimmed = text.trim();
      if (!trimmed || isSending) return;
      setInput('');
      const optimistic: AIAssistantMessage = {
        id: `temp-user-${Date.now()}`,
        role: 'user',
        content: trimmed,
        metadata_json: {},
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, optimistic]);
      setIsSending(true);
      try {
        const snapshot = getPageSnapshot();
        const conv = await sendAIAssistantMessage(trimmed, conversationId, snapshot, confirmAction);
        setConversationId(conv.id);
        setMessages(conv.messages || []);
      } catch (err) {
        const errorMessage: AIAssistantMessage = {
          id: `temp-error-${Date.now()}`,
          role: 'assistant',
          content: (err as Error)?.message || 'Failed to get assistant response.',
          metadata_json: {},
          created_at: new Date().toISOString(),
        };
        setMessages((prev) => [...prev, errorMessage]);
      } finally {
        setIsSending(false);
      }
    },
    [conversationId, isSending],
  );

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!canSend) return;
    await sendText(input);
  };

  const onNewConversation = () => {
    setMessages([]);
    setConversationId(undefined);
    setInput('');
    setHistoryOpen(false);
  };

  const onToggleHistory = () => {
    setHistoryOpen((v) => !v);
  };

  const onPickConversation = async (id: string) => {
    try {
      const conv = await loadConversation(id);
      setConversationId(conv.id);
      setMessages(conv.messages || []);
      setHistoryOpen(false);
    } catch (err) {
      setHistoryError((err as Error)?.message || 'Failed to load conversation');
    }
  };

  // Deep-link handler: ?ai_conversation=<id>&ai_message=<id>. Opens bubble,
  // loads that conversation, scrolls to the message, highlights it briefly.
  // Strips the params from the URL after handling so refresh / back doesn't
  // re-trigger.
  useEffect(() => {
    if (!canUseAIAssistant) return;
    if (!deepLinkConvId) {
      // Params cleared (either by us after handling, or by user navigation).
      // Reset the dedupe key so a subsequent click on the same link re-fires.
      handledDeepLinkRef.current = null;
      return;
    }
    const key = `${deepLinkConvId}::${deepLinkMsgId ?? ''}`;
    if (handledDeepLinkRef.current === key) return;
    handledDeepLinkRef.current = key;
    setOpenPersisted(true);
    setHistoryOpen(false);
    (async () => {
      try {
        const conv = await loadConversation(deepLinkConvId);
        setConversationId(conv.id);
        setMessages(conv.messages || []);
        if (deepLinkMsgId) {
          setHighlightedMessageId(deepLinkMsgId);
          requestAnimationFrame(() => {
            const el = messageRefs.current.get(deepLinkMsgId);
            el?.scrollIntoView({ behavior: 'smooth', block: 'center' });
          });
          window.setTimeout(() => setHighlightedMessageId(null), 4000);
        }
      } catch {
        // Ignore — keep bubble open at fresh state.
      } finally {
        const sp = new URLSearchParams(searchParams?.toString() ?? '');
        sp.delete('ai_conversation');
        sp.delete('ai_message');
        const next = sp.toString();
        router.replace(next ? `${pathname}?${next}` : pathname || '/', { scroll: false });
      }
    })();
  }, [
    canUseAIAssistant,
    deepLinkConvId,
    deepLinkMsgId,
    pathname,
    router,
    searchParams,
    setOpenPersisted,
  ]);

  const onSuggestionClick = async (s: string) => {
    setInput(s);
    await sendText(s);
  };

  // M3a Clarifier: clicking an option chip answers the clarifying question by
  // sending the option text as the next turn.
  const onClarifyOptionClick = async (opt: string) => {
    await sendText(opt);
  };

  // M3a Write-confirm: Confirm executes the pending write; Cancel drops it. The
  // message text is cosmetic — the backend keys off confirm_action + the stored
  // pending call on the prior assistant message.
  const onConfirmWrite = async () => {
    await sendText('Confirm', 'confirm');
  };
  const onCancelWrite = async () => {
    await sendText('Cancel', 'cancel');
  };

  if (!canUseAIAssistant) return null;

  return (
    // AC-N5(c): z-40, i.e. ABOVE the header (z-10) and sidebar (z-20) but BELOW
    // every Sheet / Dialog (z-50). The launcher used to be a round FAB at
    // z-[120], which floated over an open drawer's bottom controls - the reason
    // the ticket drawer's actions moved into its header in the same change.
    <div className="fixed bottom-6 end-0 z-40" data-ai-assistant-root>
      {/* Collapsed: a slim vertical handle docked to the screen edge, 32px wide,
          so the page beneath keeps its bottom-right corner (the old horizontal
          pill was ~130px wide and sat on table rows). The label rotates into the
          handle from sm up; at phone width it is the icon alone. Expanding
          replaces the handle with the panel, so the two never overlap. */}
      {open ? null : (
        <button
          ref={handleRef}
          type="button"
          data-testid="ai-assistant-tab"
          aria-label="Open AI assistant"
          aria-expanded={false}
          className={`flex w-8 flex-col items-center justify-center gap-2 rounded-s-lg border border-e-0 border-primary/20 bg-primary py-3 text-primary-foreground shadow-lg transition-all hover:w-9 ${isSending ? 'animate-pulse' : ''}`}
          onClick={() => setOpenPersisted(true)}
        >
          <Sparkles className="size-4 shrink-0" />
          <span className="hidden text-xs font-medium [writing-mode:vertical-rl] sm:inline">
            AI assistant
          </span>
        </button>
      )}

      {open ? (
        <div
          ref={panelRef}
          tabIndex={-1}
          data-testid="ai-assistant-panel"
          className="absolute bottom-0 end-3 flex flex-col overflow-hidden rounded-2xl border border-border/60 bg-gradient-to-b from-background to-muted/40 shadow-2xl backdrop-blur-sm outline-none"
          style={{
            width: `${bubbleSize.width}px`,
            height: `${bubbleSize.height}px`,
            maxWidth: 'calc(100vw - 3rem)',
            maxHeight: 'calc(100vh - 6rem)',
          }}
        >
          {/* Resize handles */}
          <div
            onMouseDown={startResize('top')}
            className="absolute left-0 right-0 top-0 z-10 h-[6px] cursor-ns-resize hover:bg-primary/20"
            aria-hidden="true"
          />
          <div
            onMouseDown={startResize('left')}
            className="absolute bottom-0 left-0 top-0 z-10 w-[6px] cursor-ew-resize hover:bg-primary/20"
            aria-hidden="true"
          />
          <div
            onMouseDown={startResize('corner')}
            className="absolute left-0 top-0 z-20 h-[12px] w-[12px] cursor-nwse-resize hover:bg-primary/30"
            aria-hidden="true"
          />

          <div className="flex items-center justify-between border-b border-border/70 bg-background/80 px-4 py-3">
            <h3 className="text-base font-semibold">AI assistant</h3>
            <div className="flex items-center gap-1">
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="size-8 rounded-full"
                onClick={onNewConversation}
                aria-label="Start new conversation"
                title="New conversation"
              >
                <Plus className="size-4" />
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="size-8 rounded-full"
                onClick={onToggleHistory}
                aria-label="Show conversation history"
                title="History"
              >
                <History className="size-4" />
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="size-8 rounded-full"
                data-testid="ai-assistant-collapse"
                onClick={() => setOpenPersisted(false)}
                aria-label="Collapse AI assistant"
                aria-expanded
                title="Collapse"
              >
                <ChevronsRight className="size-4 rtl:rotate-180" />
              </Button>
            </div>
          </div>

          {historyOpen ? (
            <div className="flex min-h-0 flex-1 flex-col">
              <div className="border-b border-border/60 bg-background/70 p-3">
                <Input
                  value={historySearch}
                  onChange={(e) => setHistorySearch(e.target.value)}
                  placeholder="Search conversations..."
                  className="rounded-xl"
                />
              </div>
              <div className="min-h-0 flex-1 overflow-y-auto p-2">
                {historyLoading ? (
                  <div className="flex items-center justify-center p-4 text-sm text-muted-foreground">
                    <Loader2 className="mr-2 size-4 animate-spin" />
                    Loading...
                  </div>
                ) : historyError ? (
                  <p className="rounded-xl bg-destructive/10 p-3 text-sm text-destructive">{historyError}</p>
                ) : historyItems.length === 0 ? (
                  <p className="rounded-xl bg-background/70 p-3 text-sm text-muted-foreground">
                    No conversations yet.
                  </p>
                ) : (
                  <ul className="space-y-1">
                    {historyItems.map((c) => (
                      <li key={c.id}>
                        <button
                          type="button"
                          onClick={() => onPickConversation(c.id)}
                          className="flex w-full flex-col items-start gap-0.5 rounded-lg px-3 py-2 text-left text-sm transition-colors hover:bg-muted/60 focus:bg-muted/60 focus:outline-none"
                        >
                          <span className="line-clamp-1 font-medium text-foreground">
                            {c.title?.trim() || 'Untitled conversation'}
                          </span>
                          <span className="text-xs text-muted-foreground">
                            {formatRelativeTime(c.updated_at)}
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          ) : (
            <>
              <div className="min-h-0 flex-1 overflow-y-auto p-4">
                <div className="space-y-3">
                  {sortedMessages.length === 0 ? (
                    <div className="space-y-3">
                      <div className="rounded-2xl bg-background/85 px-3 py-2.5 text-sm leading-relaxed shadow-sm">
                        <p className="whitespace-pre-wrap">{greeting}</p>
                      </div>
                      {greetingSuggestions.length > 0 ? (
                        <div className="flex flex-wrap gap-2">
                          {greetingSuggestions.map((s, idx) => (
                            <button
                              key={`g-${idx}-${s}`}
                              type="button"
                              onClick={() => onSuggestionClick(s)}
                              className="rounded-full border bg-secondary px-3 py-1 text-xs hover:bg-secondary/80"
                              title={s}
                            >
                              {s}
                            </button>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                  {sortedMessages.map((m, mIdx) => (
                    <div
                      key={m.id}
                      ref={(node) => {
                        if (node) messageRefs.current.set(m.id, node);
                        else messageRefs.current.delete(m.id);
                      }}
                      className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}
                    >
                      <div
                        className={`max-w-[85%] rounded-2xl px-3 py-2.5 text-sm leading-relaxed shadow-sm transition-shadow ${
                          m.role === 'user'
                            ? 'bg-primary/15 text-foreground'
                            : 'bg-background/85 text-foreground'
                        } ${highlightedMessageId === m.id ? 'ring-2 ring-primary ring-offset-2 ring-offset-background' : ''}`}
                      >
                        {m.role === 'assistant' ? (
                          <div className="ai-markdown space-y-2 [&_p]:my-0 [&_ul]:my-1 [&_ol]:my-1 [&_ul]:list-disc [&_ol]:list-decimal [&_ul]:pl-5 [&_ol]:pl-5 [&_li]:my-0.5 [&_strong]:font-semibold [&_em]:italic [&_code]:rounded [&_code]:bg-muted [&_code]:px-1 [&_code]:py-0.5 [&_code]:text-[0.9em] [&_h1]:mt-2 [&_h1]:mb-1 [&_h1]:text-base [&_h1]:font-semibold [&_h2]:mt-2 [&_h2]:mb-1 [&_h2]:text-sm [&_h2]:font-semibold [&_h3]:mt-1.5 [&_h3]:mb-0.5 [&_h3]:text-sm [&_h3]:font-semibold [&_blockquote]:border-l-2 [&_blockquote]:border-muted [&_blockquote]:pl-2 [&_blockquote]:text-muted-foreground [&_table]:my-2 [&_table]:w-full [&_th]:border [&_th]:border-border [&_th]:px-1.5 [&_th]:py-1 [&_th]:text-left [&_td]:border [&_td]:border-border [&_td]:px-1.5 [&_td]:py-1">
                            <ReactMarkdown
                              remarkPlugins={[remarkGfm]}
                              components={{
                                a: ({ href, children, ...props }) => {
                                  const url = href ?? '';
                                  const isPath = url.startsWith('/');
                                  const isHashOnly = url.startsWith('#');
                                  if (isPath) {
                                    return (
                                      <Link
                                        href={url}
                                        className="text-primary underline underline-offset-2"
                                      >
                                        {children}
                                      </Link>
                                    );
                                  }
                                  if (isHashOnly) {
                                    // Same-tab fragment link (e.g. guide_target spotlight on
                                    // the page the user is already on). Plain anchor so the
                                    // browser updates window.location.hash + fires hashchange.
                                    return (
                                      <a
                                        href={url}
                                        className="text-primary underline underline-offset-2"
                                        {...props}
                                      >
                                        {children}
                                      </a>
                                    );
                                  }
                                  return (
                                    <a
                                      href={url}
                                      target="_blank"
                                      rel="noreferrer noopener"
                                      className="text-primary underline underline-offset-2"
                                      {...props}
                                    >
                                      {children}
                                    </a>
                                  );
                                },
                              }}
                            >
                              {m.content}
                            </ReactMarkdown>
                          </div>
                        ) : (
                          <p className="whitespace-pre-wrap">{m.content}</p>
                        )}
                        {m.role === 'assistant' &&
                        canViewTrace &&
                        !m.id.startsWith('temp-') ? (
                          <div className="mt-1.5 border-t border-border/50 pt-1.5">
                            <Link
                              href={`/system-management/ai-assistant/usage/trace/${encodeURIComponent(m.id)}`}
                              target="_blank"
                              rel="noreferrer noopener"
                              className="inline-flex items-center gap-1 text-[11px] text-muted-foreground underline underline-offset-2 hover:text-primary"
                              data-testid="bubble-view-trace"
                            >
                              <GitBranch className="size-3" />
                              View trace
                            </Link>
                          </div>
                        ) : null}
                        {/* M3a Clarifier — enumerable options as clickable chips.
                            Only on the latest assistant turn (an older clarify is
                            superseded once answered). */}
                        {m.role === 'assistant' &&
                        mIdx === sortedMessages.length - 1 &&
                        !isSending &&
                        (m.metadata_json?.clarify?.options?.length ?? 0) > 0 ? (
                          <div
                            className="mt-2 flex flex-wrap gap-2"
                            data-testid="clarify-options"
                          >
                            {m.metadata_json?.clarify?.options?.map((opt, i) => (
                              <button
                                key={`${i}-${opt}`}
                                type="button"
                                onClick={() => onClarifyOptionClick(opt)}
                                className="rounded-full border bg-secondary px-3 py-1 text-xs hover:bg-secondary/80"
                                title={opt}
                              >
                                {opt}
                              </button>
                            ))}
                          </div>
                        ) : null}
                        {/* M3a Write-confirm — Confirm/Cancel for a pending write.
                            Only status === 'pending' on the latest turn shows buttons;
                            confirmed/cancelled/denied/failed are terminal. */}
                        {m.role === 'assistant' &&
                        mIdx === sortedMessages.length - 1 &&
                        !isSending &&
                        m.metadata_json?.pending_confirmation?.status === 'pending' ? (
                          <div
                            className="mt-2 flex gap-2"
                            data-testid="write-confirm-actions"
                          >
                            <button
                              type="button"
                              onClick={onConfirmWrite}
                              className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90"
                              data-testid="write-confirm-btn"
                            >
                              Confirm
                            </button>
                            <button
                              type="button"
                              onClick={onCancelWrite}
                              className="rounded-md border bg-background px-3 py-1.5 text-xs font-medium hover:bg-muted"
                              data-testid="write-cancel-btn"
                            >
                              Cancel
                            </button>
                          </div>
                        ) : null}
                        {/* Inline markdown links inside the message body are now the only
                            link surface — the previous "raw URL list" footer was redundant
                            (and confusing when the same URLs were already wrapped in the
                            markdown above). Keep `metadata_json.links` populated server-side
                            for analytics, but stop rendering the duplicate panel here. */}
                      </div>
                    </div>
                  ))}
                  {suggestions.length > 0 && !isSending ? (
                    <div className="flex flex-wrap gap-2 pt-1">
                      {suggestions.map((s, idx) => (
                        <button
                          key={`${idx}-${s}`}
                          type="button"
                          onClick={() => onSuggestionClick(s)}
                          className="rounded-full border bg-secondary px-3 py-1 text-xs hover:bg-secondary/80"
                          title={s}
                        >
                          {s}
                        </button>
                      ))}
                    </div>
                  ) : null}
                  {isSending ? (
                    <div className="flex justify-start">
                      <div className="rounded-2xl bg-background/85 p-3 text-sm shadow-sm">
                        <div className="mb-1 flex items-center gap-2 text-xs text-muted-foreground">
                          <Bot className="size-3.5 animate-pulse" />
                          Thinking...
                        </div>
                        <div className="flex items-center gap-1">
                          <span className="size-2 animate-bounce rounded-full bg-muted-foreground/70 [animation-delay:-0.3s]" />
                          <span className="size-2 animate-bounce rounded-full bg-muted-foreground/70 [animation-delay:-0.15s]" />
                          <span className="size-2 animate-bounce rounded-full bg-muted-foreground/70" />
                        </div>
                      </div>
                    </div>
                  ) : null}
                  <div ref={messagesEndRef} />
                </div>
              </div>

              <form onSubmit={onSubmit} className="border-t border-border/70 bg-background/85 p-3">
                <div className="flex items-center gap-2">
                  <Input
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    placeholder="Ask the assistant..."
                    className="rounded-xl"
                  />
                  <Button type="submit" size="icon" className="rounded-xl" disabled={!canSend}>
                    {isSending ? (
                      <Loader2 className="size-4 animate-spin" />
                    ) : (
                      <SendHorizonal className="size-4" />
                    )}
                  </Button>
                </div>
              </form>
            </>
          )}
        </div>
      ) : null}
    </div>
  );
}
