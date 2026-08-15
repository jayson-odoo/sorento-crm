'use client';

/**
 * Scroll-back + in-thread search state for a Respond.io conversation
 * (UAC AC-L7 / AC-L8).
 *
 * Shared on purpose: the intervention-ticket drawer, the SLA detail panel and
 * the complaint / stock-inquiry / purchase-request chat panels all render the
 * same `RespondChatList`, so the window management lives here rather than being
 * re-implemented per surface. A caller supplies two loaders and its live
 * (newest-window) items; everything else is this hook's job.
 *
 * Window modes
 * ------------
 * - `tail`: the window ends at the newest message. Live items (the caller's
 *   poll / push refresh) are merged in, so an inbound message still appears
 *   while the reader is scrolled up.
 * - `detached`: the reader jumped to a search match somewhere in the past. Live
 *   items are deliberately NOT merged - appending the newest messages to a
 *   window that ends in 2026-05 would look like the thread teleported. The
 *   window returns to `tail` when the reader has paged forward to the end, or
 *   when search closes.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import type { RespondMessageRenderable } from '@/lib/respondIoChatRender';
import { getRespondMessageSortTimeMs } from '@/lib/respondIoMessage';

export interface ConversationThreadPage {
  items: RespondMessageRenderable[];
  has_more_older: boolean;
  has_more_newer: boolean;
  oldest_message_id: string | null;
  newest_message_id: string | null;
  anchor_message_id?: string | null;
  error?: string | null;
}

export interface ConversationSearchMatch {
  message_id: string;
  sent_at: string | null;
  direction: string;
  snippet: string;
}

export interface ConversationThreadLoaders {
  /** The newest window, owned by the caller (its existing query keeps polling). */
  liveItems: RespondMessageRenderable[];
  loadPage: (params: {
    before?: string;
    after?: string;
    around?: string;
    limit?: number;
  }) => Promise<ConversationThreadPage>;
  searchMessages: (query: string) => Promise<ConversationSearchMatch[]>;
  /** False tears the window down (drawer closed): nothing is kept warm. */
  enabled?: boolean;
  /**
   * Identity of the conversation being shown (the ticket / entity id). Changing
   * it discards the window and any open search: a drawer that swaps tickets
   * without leaving the DOM would otherwise keep the previous contact's
   * scrolled-back pages, which is a cross-contact leak, not a stale cache.
   */
  resetKey?: string | null;
  pageSize?: number;
  /** Debounce before a keystroke becomes a request. */
  searchDebounceMs?: number;
}

/** The slice `RespondChatList` needs to render the header search affordance. */
export interface ConversationSearchController {
  open: boolean;
  query: string;
  setQuery: (next: string) => void;
  openSearch: () => void;
  closeSearch: () => void;
  matchCount: number;
  /** 1-based position of the active match, 0 when there is none. */
  activePosition: number;
  activeMessageId: string | null;
  isSearching: boolean;
  isJumping: boolean;
  error: string | null;
  next: () => void;
  previous: () => void;
}

export interface ConversationThread {
  items: RespondMessageRenderable[];
  hasMoreOlder: boolean;
  isLoadingOlder: boolean;
  loadOlder: () => void;
  atConversationStart: boolean;
  /** The term to `<mark>` inside bubbles (empty when search is closed). */
  highlightTerm: string;
  search: ConversationSearchController;
  error: string | null;
}

const DEFAULT_PAGE_SIZE = 50;
const DEFAULT_DEBOUNCE_MS = 300;

function keyOf(item: RespondMessageRenderable, index: number): string {
  return item.messageId != null ? String(item.messageId) : `idx-${index}`;
}

/**
 * Merge two windows, oldest-first, one bubble per message id.
 *
 * `respond`-sourced items win over `local` ones: the local `chat_histories`
 * mirror is text-only, so preferring it would drop an attachment that the live
 * window is already showing.
 */
export function mergeThreadItems(
  ...groups: RespondMessageRenderable[][]
): RespondMessageRenderable[] {
  const byId = new Map<string, RespondMessageRenderable>();
  const anonymous: RespondMessageRenderable[] = [];

  for (const group of groups) {
    for (const item of group) {
      if (item.messageId == null) {
        anonymous.push(item);
        continue;
      }
      const id = String(item.messageId);
      const existing = byId.get(id);
      if (!existing) {
        byId.set(id, item);
        continue;
      }
      const incomingIsRich =
        (item as { source?: string }).source !== 'local' &&
        (existing as { source?: string }).source === 'local';
      if (incomingIsRich) byId.set(id, item);
    }
  }

  return [...byId.values(), ...anonymous].sort((a, b) => {
    const ta = getRespondMessageSortTimeMs(a);
    const tb = getRespondMessageSortTimeMs(b);
    if (ta !== tb) return ta - tb;
    return (a.messageId ?? 0) - (b.messageId ?? 0);
  });
}

export function useConversationThread({
  liveItems,
  loadPage,
  searchMessages,
  enabled = true,
  resetKey = null,
  pageSize = DEFAULT_PAGE_SIZE,
  searchDebounceMs = DEFAULT_DEBOUNCE_MS,
}: ConversationThreadLoaders): ConversationThread {
  const [olderItems, setOlderItems] = useState<RespondMessageRenderable[]>([]);
  const [detachedItems, setDetachedItems] = useState<RespondMessageRenderable[] | null>(null);
  const [hasMoreOlder, setHasMoreOlder] = useState(true);
  const [isLoadingOlder, setIsLoadingOlder] = useState(false);
  const [pageError, setPageError] = useState<string | null>(null);

  const [searchOpen, setSearchOpen] = useState(false);
  const [query, setQueryState] = useState('');
  const [appliedQuery, setAppliedQuery] = useState('');
  const [matches, setMatches] = useState<ConversationSearchMatch[]>([]);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [isSearching, setIsSearching] = useState(false);
  const [isJumping, setIsJumping] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);

  // Every async result is stamped with the sequence it was requested under. A
  // slow older-page landing after a jump must not resurrect the window it was
  // asked for - the guard is on the setState, not on the request.
  const fetchSeq = useRef(0);
  const searchSeq = useRef(0);

  const reset = useCallback(() => {
    fetchSeq.current += 1;
    setOlderItems([]);
    setDetachedItems(null);
    setHasMoreOlder(true);
    setIsLoadingOlder(false);
    setPageError(null);
  }, []);

  const resetSearch = useCallback(() => {
    searchSeq.current += 1;
    setQueryState('');
    setAppliedQuery('');
    setMatches([]);
    setActiveIndex(-1);
    setSearchError(null);
    setIsSearching(false);
    setIsJumping(false);
  }, []);

  useEffect(() => {
    if (!enabled) {
      reset();
      resetSearch();
      setSearchOpen(false);
    }
  }, [enabled, reset, resetSearch]);

  // A different conversation is a different window AND a different search.
  const previousResetKey = useRef(resetKey);
  useEffect(() => {
    if (previousResetKey.current === resetKey) return;
    previousResetKey.current = resetKey;
    reset();
    resetSearch();
    setSearchOpen(false);
  }, [resetKey, reset, resetSearch]);

  const items = useMemo(() => {
    if (detachedItems) return mergeThreadItems(detachedItems);
    return mergeThreadItems(olderItems, liveItems);
  }, [detachedItems, olderItems, liveItems]);

  const oldestLoadedId = useMemo(() => {
    for (const item of items) {
      if (item.messageId != null) return String(item.messageId);
    }
    return null;
  }, [items]);

  const loadOlder = useCallback(() => {
    if (!enabled || isLoadingOlder || !hasMoreOlder) return;
    const before = oldestLoadedId;
    if (!before) return;
    const seq = (fetchSeq.current += 1);
    setIsLoadingOlder(true);
    setPageError(null);
    void loadPage({ before, limit: pageSize })
      .then((page) => {
        if (seq !== fetchSeq.current) return;
        if (detachedItems) {
          setDetachedItems((current) =>
            current ? mergeThreadItems(page.items, current) : page.items,
          );
        } else {
          setOlderItems((current) => mergeThreadItems(page.items, current));
        }
        setHasMoreOlder(Boolean(page.has_more_older));
      })
      .catch((error: unknown) => {
        if (seq !== fetchSeq.current) return;
        setPageError(error instanceof Error ? error.message : 'Failed to load older messages.');
      })
      .finally(() => {
        if (seq !== fetchSeq.current) return;
        setIsLoadingOlder(false);
      });
  }, [
    enabled,
    isLoadingOlder,
    hasMoreOlder,
    oldestLoadedId,
    loadPage,
    pageSize,
    detachedItems,
  ]);

  // ---- search ------------------------------------------------------------

  const setQuery = useCallback((next: string) => {
    setQueryState(next);
  }, []);

  useEffect(() => {
    if (!searchOpen || !enabled) return;
    const trimmed = query.trim();
    if (!trimmed) {
      searchSeq.current += 1;
      setMatches([]);
      setActiveIndex(-1);
      setAppliedQuery('');
      setIsSearching(false);
      setSearchError(null);
      return;
    }
    const handle = setTimeout(() => {
      const seq = (searchSeq.current += 1);
      setIsSearching(true);
      setSearchError(null);
      void searchMessages(trimmed)
        .then((found) => {
          if (seq !== searchSeq.current) return;
          setMatches(found);
          setAppliedQuery(trimmed);
          setActiveIndex(found.length > 0 ? 0 : -1);
        })
        .catch((error: unknown) => {
          if (seq !== searchSeq.current) return;
          setMatches([]);
          setActiveIndex(-1);
          setSearchError(error instanceof Error ? error.message : 'Search failed.');
        })
        .finally(() => {
          if (seq !== searchSeq.current) return;
          setIsSearching(false);
        });
    }, searchDebounceMs);
    return () => clearTimeout(handle);
  }, [query, searchOpen, enabled, searchMessages, searchDebounceMs]);

  const loadedIds = useMemo(
    () =>
      new Set(
        items
          .filter((item) => item.messageId != null)
          .map((item) => String(item.messageId)),
      ),
    [items],
  );

  const activeMessageId = activeIndex >= 0 ? (matches[activeIndex]?.message_id ?? null) : null;

  // Jump: an already-rendered match only needs the scroll (RespondChatList owns
  // that); one outside the window needs the server-centred page, which REPLACES
  // the window rather than being spliced into it - a window with a hole in the
  // middle would render as a silent gap in the conversation.
  useEffect(() => {
    if (!enabled || !activeMessageId) return;
    if (loadedIds.has(activeMessageId)) return;
    const seq = (fetchSeq.current += 1);
    setIsJumping(true);
    void loadPage({ around: activeMessageId, limit: pageSize })
      .then((page) => {
        if (seq !== fetchSeq.current) return;
        setDetachedItems(page.items);
        setOlderItems([]);
        setHasMoreOlder(Boolean(page.has_more_older));
      })
      .catch((error: unknown) => {
        if (seq !== fetchSeq.current) return;
        setSearchError(error instanceof Error ? error.message : 'Could not open that message.');
      })
      .finally(() => {
        if (seq !== fetchSeq.current) return;
        setIsJumping(false);
      });
  }, [activeMessageId, loadedIds, enabled, loadPage, pageSize]);

  const openSearch = useCallback(() => setSearchOpen(true), []);

  const closeSearch = useCallback(() => {
    setSearchOpen(false);
    resetSearch();
    // Back to the live tail: closing search should land the reader where the
    // conversation actually is, not where they were reading history.
    reset();
  }, [reset, resetSearch]);

  const step = useCallback(
    (delta: number) => {
      setActiveIndex((current) => {
        if (matches.length === 0) return -1;
        const base = current < 0 ? 0 : current;
        return (base + delta + matches.length) % matches.length;
      });
    },
    [matches.length],
  );

  // Matches come back newest-first, so "next" (the down chevron, toward newer)
  // walks the list backwards and "previous" (up, toward older) walks forwards.
  const next = useCallback(() => step(-1), [step]);
  const previous = useCallback(() => step(1), [step]);

  return {
    items,
    hasMoreOlder: enabled && hasMoreOlder,
    isLoadingOlder,
    loadOlder,
    atConversationStart: !hasMoreOlder && items.length > 0,
    highlightTerm: searchOpen ? appliedQuery : '',
    error: pageError,
    search: {
      open: searchOpen,
      query,
      setQuery,
      openSearch,
      closeSearch,
      matchCount: matches.length,
      activePosition: activeIndex >= 0 ? activeIndex + 1 : 0,
      activeMessageId,
      isSearching,
      isJumping,
      error: searchError,
      next,
      previous,
    },
  };
}

export { keyOf as conversationItemKey, DEFAULT_PAGE_SIZE as CONVERSATION_PAGE_SIZE };
