'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Textarea } from '@/components/ui/textarea';
import RespondChatList from '@/components/common/RespondChatList';
import {
  useConversationThread,
  type ConversationThreadLoaders,
} from '@/components/common/conversation/useConversationThread';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import type { RespondMessageRenderable } from '@/lib/respondIoChatRender';
import type { StockAsk } from '@/lib/stock-asks';
import { askAnswerText, askProductText, type AskConversation } from '@/lib/stock-asks-todo';

/** Where the CRM's chat history for one contact lives. */
const CONVERSATIONS_PATH = '/sla-management/conversations';

/**
 * What the mount hands the panel about the ask's contact thread (ASKS-UX item 3): the live tail
 * it keeps polling, plus the two loaders `useConversationThread` needs for scroll-back, search
 * and the jump to the anchor. The mount owns the fetching (portal token or CRM session).
 */
export interface AskThreadSource {
  liveItems: RespondMessageRenderable[];
  /** True until the tail has been read once. */
  loading: boolean;
  /** The tail read failed: shown in place of the thread. */
  error: string | null;
  loadPage: ConversationThreadLoaders['loadPage'];
  searchMessages: ConversationThreadLoaders['searchMessages'];
}

export interface AskConversationPanelProps {
  ask: StockAsk;
  /** The anchor read: `ask_message_ref` tags the bubble; `contact_id` feeds the CRM link. */
  conversation: AskConversation | undefined;
  thread: AskThreadSource;
  /** CRM only: the link to that contact's chat history. */
  showOpenInConversations: boolean;
  /** CRM only: the agent's code, on the header line. */
  agentCode?: string | null;
  /** Saves the note; a rejection is the caller's to report, "Saved" shows only after it resolves. */
  onNote: (askId: string, note: string) => Promise<unknown> | void;
  onDone: (askId: string) => void;
  onReopen: (askId: string) => void;
  pending?: boolean;
}

/**
 * The body of the opened card (portal Drawer, CRM Sheet): who and when, the Asked / Answered
 * block, the contact's whole thread (the SAME `RespondChatList` + `useConversationThread` the
 * ticket drawer mounts: scroll-back, search, jump to latest, the anchor tagged "This enquiry"),
 * an explicit-save Note and the Done / Reopen foot. Read-only: no composer. Presentational:
 * the mount fetches and owns the drawer.
 */
export function AskConversationPanel({
  ask,
  conversation,
  thread: source,
  showOpenInConversations,
  agentCode,
  onNote,
  onDone,
  onReopen,
  pending = false,
}: AskConversationPanelProps) {
  const [note, setNote] = useState(ask.note ?? '');
  const [savedAt, setSavedAt] = useState<Date | null>(null);
  const [saving, setSaving] = useState(false);

  const isDone = ask.state === 'done';
  const anchor = conversation?.ask_message_ref ?? null;

  const thread = useConversationThread({
    liveItems: source.liveItems,
    loadPage: source.loadPage,
    searchMessages: source.searchMessages,
    resetKey: ask.id,
  });
  const { jumpToMessage } = thread;

  // On open the thread lands on the anchor once the tail is in: a scroll when the tail holds it,
  // the page around it (a detached window with "Jump to latest") when it does not. Waiting for
  // the tail is what stops an empty window from fetching the around-page for nothing.
  const jumpedTo = useRef<string | null>(null);
  useEffect(() => {
    if (!anchor || source.loading || jumpedTo.current === anchor) return;
    jumpedTo.current = anchor;
    jumpToMessage(anchor);
  }, [anchor, source.loading, jumpToMessage]);

  const saveNote = async () => {
    setSaving(true);
    try {
      await onNote(ask.id, note.trim());
      setSavedAt(new Date());
    } catch {
      // The mount toasts the failure; nothing is shown as saved.
    } finally {
      setSaving(false);
    }
  };

  const href = conversation?.contact_id
    ? `${CONVERSATIONS_PATH}?contact=${encodeURIComponent(conversation.contact_id)}`
    : CONVERSATIONS_PATH;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-3">
        <header className="space-y-0.5">
          <p className="text-base">
            <span className="font-semibold">{ask.customer_name || ask.contact_name || '-'}</span>
          </p>
          {ask.contact_name || ask.contact_phone ? (
            <p className="text-sm text-muted-foreground">
              {[ask.customer_name ? ask.contact_name : null, ask.contact_phone].filter(Boolean).join(' · ')}
            </p>
          ) : null}
          <p className="text-xs text-muted-foreground">
            Asked {formatDateTimeInMalaysia(ask.created_at)}
            {agentCode ? ` · ${agentCode}` : ''}
          </p>
        </header>

        <div className="space-y-1 rounded-lg border bg-muted/40 px-3 py-2.5">
          <p className="text-sm break-words">
            Asked: {askProductText(ask)}
            {ask.product_name ? ` (${ask.product_name})` : ''}
          </p>
          <p className="text-sm break-words">
            <span className="text-muted-foreground">Answered: </span>
            {askAnswerText(ask)}
          </p>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="-ml-2"
            onClick={() => jumpToMessage(anchor)}
            disabled={anchor == null}
          >
            Jump to message
          </Button>
        </div>

        <section className="space-y-2" aria-label="Conversation">
          <h3 className="text-sm font-semibold">Conversation</h3>
          {source.loading && source.liveItems.length === 0 ? (
            <div className="space-y-2" role="status" aria-label="Loading">
              <Skeleton className="h-9 w-2/3" />
              <Skeleton className="ml-auto h-9 w-2/3" />
              <Skeleton className="h-9 w-1/2" />
            </div>
          ) : source.error ? (
            <p className="text-sm text-destructive">{source.error}</p>
          ) : (
            <>
              {thread.error ? <p className="text-xs text-destructive">{thread.error}</p> : null}
              <RespondChatList
                items={thread.items}
                contactName={ask.contact_name}
                contactPhone={ask.contact_phone}
                emptyHint="No messages in this conversation yet."
                maxHeightClass="max-h-[50vh]"
                highlightMessageId={anchor}
                highlightLabel="This enquiry"
                onLoadOlder={thread.loadOlder}
                hasMoreOlder={thread.hasMoreOlder}
                isLoadingOlder={thread.isLoadingOlder}
                atConversationStart={thread.atConversationStart}
                isDetached={thread.isDetached}
                onJumpToLatest={thread.jumpToLatest}
                newerUnseenCount={thread.newerUnseenCount}
                onLoadNewer={thread.loadNewer}
                hasMoreNewer={thread.hasMoreNewer}
                isLoadingNewer={thread.isLoadingNewer}
                searchController={thread.search}
                highlightTerm={thread.highlightTerm}
                focusMessageId={thread.focusMessageId}
                focusNonce={thread.focusNonce}
                onJumpToMessage={thread.jumpToMessage}
              />
            </>
          )}
          {showOpenInConversations ? (
            <Link href={href} className="inline-block text-sm text-primary underline-offset-4 hover:underline">
              Open in Conversations
            </Link>
          ) : null}
        </section>

        <section className="space-y-1.5">
          <label htmlFor={`ask-note-${ask.id}`} className="text-sm font-semibold">
            Note
          </label>
          <Textarea
            id={`ask-note-${ask.id}`}
            value={note}
            rows={3}
            onChange={(e) => {
              setNote(e.target.value);
              setSavedAt(null);
            }}
          />
          <div className="flex items-center gap-3">
            <Button type="button" size="sm" variant="outline" disabled={saving} onClick={saveNote}>
              Save note
            </Button>
            {savedAt ? (
              <span className="text-xs text-muted-foreground">Saved {formatDateTimeInMalaysia(savedAt)}</span>
            ) : null}
          </div>
        </section>
      </div>

      <div className="border-t px-4 py-3">
        {isDone ? (
          <Button type="button" variant="outline" className="w-full" disabled={pending} onClick={() => onReopen(ask.id)}>
            Reopen
          </Button>
        ) : (
          <Button type="button" variant="primary" className="w-full" disabled={pending} onClick={() => onDone(ask.id)}>
            Done
          </Button>
        )}
      </div>
    </div>
  );
}
