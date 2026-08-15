'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AlertCircle, ArrowDownLeft, ArrowUpRight, Loader2, Search } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { formatDateTimeInMalaysia, parseDateTimeAsUTC, timeAgo } from '@/lib/helpers';
import { cn } from '@/lib/utils';

import { useConversationsInbox } from '../hooks/useConversationsInbox';
import {
  CONVERSATION_INBOX_TABS,
  type ConversationInboxItem,
  type ConversationInboxTab,
} from '../services/conversationsInboxService';

const TAB_LABELS: Record<ConversationInboxTab, string> = {
  mine: 'Mine',
  mentioned: 'Mentioned',
  unassigned: 'Unassigned',
  all: 'All',
};

const EMPTY_COPY: Record<ConversationInboxTab, string> = {
  mine: 'No conversations with an open enquiry of yours.',
  mentioned: 'Nobody has mentioned you in a note yet.',
  unassigned: 'No open enquiry is waiting for an owner.',
  all: 'No conversations yet.',
};

/** How long a keystroke waits before it becomes a request. */
const SEARCH_DEBOUNCE_MS = 300;
/** Distance from the bottom that pulls the next page in. */
const LOAD_MORE_THRESHOLD_PX = 120;

interface ConversationListPaneProps {
  tab: ConversationInboxTab;
  onTabChange: (tab: ConversationInboxTab) => void;
  selectedRef: string | null;
  onSelect: (item: ConversationInboxItem) => void;
  className?: string;
}

function rowTitle(item: ConversationInboxItem): string {
  return item.name?.trim() || item.phone?.trim() || 'Unknown contact';
}

/**
 * The left pane (UAC AC-N1): server-paginated, searchable, tabbed. It never
 * fetches a thread - that is the right pane's job, and only for the row the
 * user picked. At 10 000 contacts this stays one list query per page.
 */
export default function ConversationListPane({
  tab,
  onTabChange,
  selectedRef,
  onSelect,
  className,
}: ConversationListPaneProps) {
  const [searchText, setSearchText] = useState('');
  const [appliedQuery, setAppliedQuery] = useState('');
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handle = setTimeout(() => setAppliedQuery(searchText.trim()), SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(handle);
  }, [searchText]);

  const query = useConversationsInbox(tab, appliedQuery);
  const items = useMemo(
    () => (query.data?.pages ?? []).flatMap((page) => page.items),
    [query.data],
  );

  const { fetchNextPage, hasNextPage, isFetchingNextPage } = query;
  const loadMore = useCallback(() => {
    if (!hasNextPage || isFetchingNextPage) return;
    void fetchNextPage();
  }, [fetchNextPage, hasNextPage, isFetchingNextPage]);

  // Infinite scroll, with the explicit button below as the always-visible way
  // to do the same thing (a scroll handler alone is invisible on a short list
  // and unreachable with a keyboard).
  const handleScroll = useCallback(() => {
    const node = scrollRef.current;
    if (!node) return;
    const distanceFromBottom = node.scrollHeight - node.scrollTop - node.clientHeight;
    if (distanceFromBottom <= LOAD_MORE_THRESHOLD_PX) loadMore();
  }, [loadMore]);

  const isInitialLoading = query.isLoading;
  const isEmpty = !isInitialLoading && !query.isError && items.length === 0;

  return (
    <div className={cn('flex min-h-0 flex-col gap-3', className)}>
      <div
        role="tablist"
        aria-label="Conversation filter"
        className="flex w-full gap-1 rounded-md border bg-muted/40 p-1"
      >
        {CONVERSATION_INBOX_TABS.map((value) => (
          <button
            key={value}
            type="button"
            role="tab"
            aria-selected={tab === value}
            data-testid={`inbox-tab-${value}`}
            onClick={() => onTabChange(value)}
            className={cn(
              'flex-1 rounded px-2 py-1.5 text-xs font-medium transition-colors sm:text-sm',
              tab === value
                ? 'bg-background text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground',
            )}
          >
            {TAB_LABELS[value]}
          </button>
        ))}
      </div>

      <div className="relative">
        <Search className="pointer-events-none absolute start-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={searchText}
          onChange={(e) => setSearchText(e.target.value)}
          placeholder="Search name or phone"
          aria-label="Search conversations"
          data-testid="inbox-search"
          className="ps-8"
        />
      </div>

      <div
        ref={scrollRef}
        onScroll={handleScroll}
        data-testid="inbox-list-scroll"
        className="min-h-0 flex-1 overflow-y-auto rounded-md border"
      >
        {isInitialLoading && (
          <div className="space-y-2 p-3" data-testid="inbox-loading">
            <Skeleton className="h-14 w-full" />
            <Skeleton className="h-14 w-full" />
            <Skeleton className="h-14 w-full" />
          </div>
        )}

        {query.isError && (
          <div
            data-testid="inbox-error"
            className="m-3 flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive"
          >
            <AlertCircle className="mt-0.5 size-4 shrink-0" />
            <div className="min-w-0">
              <p>
                {query.error instanceof Error
                  ? query.error.message
                  : 'Failed to load conversations.'}
              </p>
              <Button
                size="sm"
                variant="outline"
                className="mt-2 h-7"
                onClick={() => void query.refetch()}
              >
                Try again
              </Button>
            </div>
          </div>
        )}

        {isEmpty && (
          <p
            data-testid="inbox-empty"
            className="p-6 text-center text-sm text-muted-foreground"
          >
            {appliedQuery
              ? `No conversation matches "${appliedQuery}".`
              : EMPTY_COPY[tab]}
          </p>
        )}

        <ul className="divide-y">
          {items.map((item) => {
            const selected = selectedRef === item.contact_ref;
            const stamp = item.mentioned_at ?? item.last_message_at;
            return (
              <li key={item.contact_ref}>
                <button
                  type="button"
                  data-testid={`inbox-row-${item.contact_ref}`}
                  data-selected={selected ? 'true' : undefined}
                  aria-current={selected ? 'true' : undefined}
                  onClick={() => onSelect(item)}
                  className={cn(
                    'flex w-full flex-col gap-1 px-3 py-2.5 text-start transition-colors hover:bg-muted/60',
                    selected && 'bg-primary/10 hover:bg-primary/10',
                  )}
                >
                  <span className="flex items-center gap-2">
                    <span className="min-w-0 flex-1 truncate text-sm font-medium">
                      {rowTitle(item)}
                    </span>
                    {item.open_ticket_count > 0 && (
                      <span
                        data-testid={`inbox-open-count-${item.contact_ref}`}
                        title={`${item.open_ticket_count} open enquiry${item.open_ticket_count > 1 ? 's' : ''}`}
                        className="shrink-0 rounded-full bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold text-amber-800 dark:bg-amber-900/50 dark:text-amber-200"
                      >
                        {item.open_ticket_count} open
                      </span>
                    )}
                    {stamp && (
                      <span
                        className="shrink-0 text-[11px] text-muted-foreground"
                        title={formatDateTimeInMalaysia(stamp)}
                      >
                        {timeAgo(parseDateTimeAsUTC(stamp))}
                      </span>
                    )}
                  </span>
                  {item.name?.trim() && item.phone?.trim() && (
                    <span className="truncate text-xs text-muted-foreground">{item.phone}</span>
                  )}
                  <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                    {item.last_message_direction === 'outgoing' ? (
                      <ArrowUpRight
                        className="size-3 shrink-0"
                        aria-label="Last message was outgoing"
                      />
                    ) : item.last_message_direction === 'incoming' ? (
                      <ArrowDownLeft
                        className="size-3 shrink-0"
                        aria-label="Last message was incoming"
                      />
                    ) : null}
                    <span className="min-w-0 truncate">
                      {item.last_message_snippet?.trim() || 'No messages yet'}
                    </span>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>

        {hasNextPage && (
          <div className="p-3">
            <Button
              variant="outline"
              size="sm"
              className="w-full"
              data-testid="inbox-load-more"
              disabled={isFetchingNextPage}
              onClick={loadMore}
            >
              {isFetchingNextPage && <Loader2 className="size-3.5 animate-spin" />}
              {isFetchingNextPage ? 'Loading' : 'Load more'}
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
