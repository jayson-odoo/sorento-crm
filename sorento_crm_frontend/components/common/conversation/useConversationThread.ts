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
 *   window that ends in 2026-05 would look like the thread teleported. Instead
 *   `newerUnseenCount` says how many live messages the reader cannot currently
 *   see, and there are two ways back: `loadNewer()` pages forward one page at a
 *   time (the window rejoins the tail by itself once a page reports nothing
 *   newer), and `jumpToLatest()` drops the window and lands on the live tail in
 *   one step. Closing search also returns to `tail`.
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
  /** True while the window sits in the past instead of on the live tail. */
  isDetached: boolean;
  hasMoreNewer: boolean;
  isLoadingNewer: boolean;
  loadNewer: () => void;
  /** Drop the detached window and land back on the live tail. */
  jumpToLatest: () => void;
  /** Live messages the detached window is hiding. 0 in tail mode. */
  newerUnseenCount: number;
  /** The term to `<mark>` inside bubbles (empty when search is closed). */
  highlightTerm: string;
  search: ConversationSearchController;
  error: string | null;
  /**
   * Scroll to one message by id and flash it (AC-N6), loading the surrounding
   * page first when it is outside the window - the same mechanism a search jump
   * uses, exposed for callers with their own entry point (the drawer's quoted
   * enquiry). A no-op for an empty id.
   */
  jumpToMessage: (messageId: string | number | null | undefined) => void;
  /** The message `RespondChatList` should scroll to and ring. */
  focusMessageId: string | null;
  /**
   * Bumped on every `jumpToMessage` call, INCLUDING a repeat of the same id -
   * clicking the enquiry twice must scroll back twice, and an id alone cannot
   * express that.
   */
  focusNonce: number;
  /** True while the around-page for a jump target is in flight. */
  isJumpingToMessage: boolean;
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
  const [hasMoreNewer, setHasMoreNewer] = useState(false);
  const [isLoadingOlder, setIsLoadingOlder] = useState(false);
  const [isLoadingNewer, setIsLoadingNewer] = useState(false);
  const [pageError, setPageError] = useState<string | null>(null);

  // AC-N6: a caller-driven jump (the drawer's quoted enquiry). Kept apart from
  // the search cursor: the two can be pointed at different messages, and a jump
  // must not disturb an open search's active match.
  const [focus, setFocus] = useState<{ messageId: string | null; nonce: number }>({
    messageId: null,
    nonce: 0,
  });
  const [isJumpingToMessage, setIsJumpingToMessage] = useState(false);
  const focusToken = useRef<number | null>(null);

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
  // asked for - the guard is on the DATA SETTERS only. Whether a lane is busy is
  // a separate question, owned per lane by the token refs below: a superseded
  // request still has to put its own spinner away, or the reader is left with a
  // scroll-back that never fires again.
  const fetchSeq = useRef(0);
  const searchSeq = useRef(0);
  // Per-lane in-flight token. Null = idle, which is also the guard against a
  // second request: `isLoadingOlder` is state, and a burst of scroll events in
  // one frame all read it from the render they were queued in.
  const olderToken = useRef<number | null>(null);
  const newerToken = useRef<number | null>(null);
  const jumpToken = useRef<number | null>(null);
  const tokenCounter = useRef(0);
  const nextToken = () => (tokenCounter.current += 1);
  // The detached window, readable at promise-resolution time. The state copy is
  // a render behind, and both page lanes merge into whatever the window holds
  // NOW - an older page landing while a newer one is in flight must not be lost.
  const detachedRef = useRef<RespondMessageRenderable[] | null>(null);
  const setDetached = useCallback((next: RespondMessageRenderable[] | null) => {
    detachedRef.current = next;
    setDetachedItems(next);
  }, []);
  // The match we have already fetched a page for. Keyed on the match id, NOT on
  // "is it loaded": an around-page that comes back without its anchor (purged
  // message, scope change) would otherwise be re-requested on every poll tick.
  const jumpedTo = useRef<string | null>(null);

  const reset = useCallback(() => {
    fetchSeq.current += 1;
    olderToken.current = null;
    newerToken.current = null;
    setOlderItems([]);
    setDetached(null);
    setHasMoreOlder(true);
    setHasMoreNewer(false);
    setIsLoadingOlder(false);
    setIsLoadingNewer(false);
    setPageError(null);
    focusToken.current = null;
    setIsJumpingToMessage(false);
    setFocus((current) => (current.messageId === null ? current : { messageId: null, nonce: current.nonce }));
  }, [setDetached]);

  const resetSearch = useCallback(() => {
    searchSeq.current += 1;
    fetchSeq.current += 1;
    jumpToken.current = null;
    jumpedTo.current = null;
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

  const newestLoadedId = useMemo(() => {
    for (let i = items.length - 1; i >= 0; i -= 1) {
      if (items[i].messageId != null) return String(items[i].messageId);
    }
    return null;
  }, [items]);

  const loadOlder = useCallback(() => {
    if (!enabled || olderToken.current !== null || !hasMoreOlder) return;
    const before = oldestLoadedId;
    if (!before) return;
    const token = nextToken();
    olderToken.current = token;
    const seq = (fetchSeq.current += 1);
    setIsLoadingOlder(true);
    setPageError(null);
    void loadPage({ before, limit: pageSize })
      .then((page) => {
        if (seq !== fetchSeq.current) return;
        if (detachedRef.current) {
          setDetached(mergeThreadItems(page.items, detachedRef.current));
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
        // The flag belongs to THIS request, never to the sequence: a superseded
        // page still has to put the spinner away. A reset drops the token, so a
        // straggler cannot clear a flag a newer request has already raised.
        if (olderToken.current !== token) return;
        olderToken.current = null;
        setIsLoadingOlder(false);
      });
  }, [enabled, hasMoreOlder, oldestLoadedId, loadPage, pageSize, setDetached]);

  /**
   * Page forward out of a detached window. Once a page reports nothing newer
   * the window rejoins the tail: everything paged through is kept, and live
   * items merge again so inbound messages appear on their own after that.
   */
  const loadNewer = useCallback(() => {
    if (!enabled || newerToken.current !== null || !hasMoreNewer) return;
    if (!detachedRef.current) return;
    const after = newestLoadedId;
    if (!after) return;
    const token = nextToken();
    newerToken.current = token;
    const seq = (fetchSeq.current += 1);
    setIsLoadingNewer(true);
    setPageError(null);
    void loadPage({ after, limit: pageSize })
      .then((page) => {
        if (seq !== fetchSeq.current) return;
        const merged = mergeThreadItems(detachedRef.current ?? [], page.items);
        if (page.has_more_newer) {
          setDetached(merged);
        } else {
          setOlderItems(merged);
          setDetached(null);
        }
        setHasMoreNewer(Boolean(page.has_more_newer));
      })
      .catch((error: unknown) => {
        if (seq !== fetchSeq.current) return;
        setPageError(error instanceof Error ? error.message : 'Failed to load newer messages.');
      })
      .finally(() => {
        if (newerToken.current !== token) return;
        newerToken.current = null;
        setIsLoadingNewer(false);
      });
  }, [enabled, hasMoreNewer, newestLoadedId, loadPage, pageSize, setDetached]);

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

  // Readable at click time: `loadedIds` is a render-time memo, and a jump is
  // triggered from an event handler that must decide "is it already here?"
  // against the window as it stands NOW.
  const loadedIdsRef = useRef(loadedIds);
  useEffect(() => {
    loadedIdsRef.current = loadedIds;
  }, [loadedIds]);

  /**
   * AC-N6. Point the list at one message. Already in the window -> the list
   * just scrolls and flashes it. Outside -> the server-centred page REPLACES
   * the window first (same reasoning as the search jump: a window with a hole
   * in the middle renders as a silent gap), and the list scrolls once the
   * bubble mounts.
   */
  const jumpToMessage = useCallback(
    (messageId: string | number | null | undefined) => {
      if (!enabled) return;
      const target = messageId == null ? '' : String(messageId).trim();
      if (!target) return;
      setFocus((current) => ({ messageId: target, nonce: current.nonce + 1 }));
      if (loadedIdsRef.current.has(target)) return;

      const token = nextToken();
      focusToken.current = token;
      const seq = (fetchSeq.current += 1);
      setIsJumpingToMessage(true);
      setPageError(null);
      void loadPage({ around: target, limit: pageSize })
        .then((page) => {
          if (seq !== fetchSeq.current) return;
          setDetached(page.items);
          setOlderItems([]);
          setHasMoreOlder(Boolean(page.has_more_older));
          setHasMoreNewer(Boolean(page.has_more_newer));
        })
        .catch((error: unknown) => {
          if (seq !== fetchSeq.current) return;
          setPageError(
            error instanceof Error ? error.message : 'Could not open that message.',
          );
        })
        .finally(() => {
          if (focusToken.current !== token) return;
          focusToken.current = null;
          setIsJumpingToMessage(false);
        });
    },
    [enabled, loadPage, pageSize, setDetached],
  );

  // What the detached window is hiding: live messages that are not in it. The
  // reader gets a count, not a silent gap.
  const newerUnseenCount = useMemo(() => {
    if (!detachedItems) return 0;
    let unseen = 0;
    for (const item of liveItems) {
      if (item.messageId == null) continue;
      if (!loadedIds.has(String(item.messageId))) unseen += 1;
    }
    return unseen;
  }, [detachedItems, liveItems, loadedIds]);

  const activeMessageId = activeIndex >= 0 ? (matches[activeIndex]?.message_id ?? null) : null;

  // Jump: an already-rendered match only needs the scroll (RespondChatList owns
  // that); one outside the window needs the server-centred page, which REPLACES
  // the window rather than being spliced into it - a window with a hole in the
  // middle would render as a silent gap in the conversation.
  useEffect(() => {
    if (!enabled || !activeMessageId) return;
    if (jumpedTo.current === activeMessageId) return;
    if (loadedIds.has(activeMessageId)) {
      jumpedTo.current = activeMessageId;
      return;
    }
    // Marked BEFORE the request and left marked on failure: a page that comes
    // back without the anchor must not be asked for again on the next tick.
    jumpedTo.current = activeMessageId;
    const token = nextToken();
    jumpToken.current = token;
    const seq = (fetchSeq.current += 1);
    setIsJumping(true);
    void loadPage({ around: activeMessageId, limit: pageSize })
      .then((page) => {
        if (seq !== fetchSeq.current) return;
        setDetached(page.items);
        setOlderItems([]);
        setHasMoreOlder(Boolean(page.has_more_older));
        setHasMoreNewer(Boolean(page.has_more_newer));
      })
      .catch((error: unknown) => {
        if (seq !== fetchSeq.current) return;
        setSearchError(error instanceof Error ? error.message : 'Could not open that message.');
      })
      .finally(() => {
        if (jumpToken.current !== token) return;
        jumpToken.current = null;
        setIsJumping(false);
      });
  }, [activeMessageId, loadedIds, enabled, loadPage, pageSize, setDetached]);

  /**
   * Straight back to the live tail from a detached window. The search bar stays
   * open with its matches - only the cursor is dropped, so the jump effect does
   * not immediately pull the reader back into the past.
   */
  const jumpToLatest = useCallback(() => {
    reset();
    jumpToken.current = null;
    jumpedTo.current = null;
    setActiveIndex(-1);
    setIsJumping(false);
  }, [reset]);

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
    isDetached: detachedItems !== null,
    hasMoreNewer: enabled && hasMoreNewer,
    isLoadingNewer,
    loadNewer,
    jumpToLatest,
    newerUnseenCount,
    highlightTerm: searchOpen ? appliedQuery : '',
    error: pageError,
    jumpToMessage,
    focusMessageId: focus.messageId,
    focusNonce: focus.nonce,
    isJumpingToMessage,
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
