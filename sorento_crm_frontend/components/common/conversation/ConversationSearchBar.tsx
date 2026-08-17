'use client';

/**
 * WhatsApp-style in-thread search bar (UAC AC-L8).
 *
 * Rendered by `RespondChatList` under its contact header, so every surface that
 * uses the shared chat list gets the same bar. It is presentation only: the
 * query, the match set and the cursor all live in `useConversationThread`.
 */

import { useEffect, useRef } from 'react';
import { ChevronDown, ChevronUp, Loader2, Search, X } from 'lucide-react';

import type { ConversationSearchController } from './useConversationThread';

export default function ConversationSearchBar({
  controller,
}: {
  controller: ConversationSearchController;
}) {
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (controller.open) inputRef.current?.focus?.();
  }, [controller.open]);

  if (!controller.open) return null;

  const hasQuery = controller.query.trim().length > 0;
  const busy = controller.isSearching || controller.isJumping;
  const noMatches = hasQuery && !busy && controller.matchCount === 0;

  return (
    <div className="border-x border-b bg-[#f0f2f5] px-3 py-2 dark:bg-[#202c33]">
      <div className="flex items-center gap-2" data-testid="conversation-search-controls">
        <Search className="size-4 shrink-0 text-zinc-500 dark:text-zinc-400" aria-hidden />
        <input
          ref={inputRef}
          type="search"
          role="searchbox"
          aria-label="Search messages"
          value={controller.query}
          placeholder="Search messages"
          className="min-w-0 flex-1 bg-transparent text-sm text-zinc-900 outline-none placeholder:text-zinc-500 dark:text-zinc-100"
          onChange={(e) => controller.setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Escape') {
              e.preventDefault();
              controller.closeSearch();
              return;
            }
            if (e.key === 'Enter') {
              e.preventDefault();
              if (e.shiftKey) controller.previous();
              else controller.next();
            }
          }}
        />

        {busy && <Loader2 className="size-4 shrink-0 animate-spin text-zinc-500" aria-label="Searching" />}

        {hasQuery && !busy && (
          <span
            className="shrink-0 whitespace-nowrap text-xs tabular-nums text-zinc-600 dark:text-zinc-300"
            data-testid="conversation-search-counter"
          >
            {noMatches ? 'No results' : `${controller.activePosition} / ${controller.matchCount}`}
          </span>
        )}

        <button
          type="button"
          aria-label="Previous match"
          disabled={controller.matchCount === 0}
          onClick={controller.previous}
          className="shrink-0 rounded p-1 text-zinc-600 hover:bg-black/5 disabled:opacity-40 dark:text-zinc-300 dark:hover:bg-white/10"
        >
          <ChevronUp className="size-4" />
        </button>
        <button
          type="button"
          aria-label="Next match"
          disabled={controller.matchCount === 0}
          onClick={controller.next}
          className="shrink-0 rounded p-1 text-zinc-600 hover:bg-black/5 disabled:opacity-40 dark:text-zinc-300 dark:hover:bg-white/10"
        >
          <ChevronDown className="size-4" />
        </button>
        <button
          type="button"
          aria-label="Close search"
          onClick={controller.closeSearch}
          className="shrink-0 rounded p-1 text-zinc-600 hover:bg-black/5 dark:text-zinc-300 dark:hover:bg-white/10"
        >
          <X className="size-4" />
        </button>
      </div>

      {/* Its own line: in the control row a failure message pushed the bar
          wider than the drawer at phone width. */}
      {controller.error && (
        <p className="mt-1 text-xs text-destructive" data-testid="conversation-search-error">
          {controller.error}
        </p>
      )}
    </div>
  );
}
