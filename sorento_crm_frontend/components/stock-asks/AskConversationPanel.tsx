'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Textarea } from '@/components/ui/textarea';
import { formatChatDayPillMalaysia, formatDateInMalaysia, formatDateTimeInMalaysia, formatTimeShortMalaysia } from '@/lib/helpers';
import type { StockAsk } from '@/lib/stock-asks';
import {
  askAnswerText,
  askProductText,
  utcMs,
  type AskConversation,
} from '@/lib/stock-asks-todo';
import { cn } from '@/lib/utils';

/** Where the CRM's chat history for one contact lives. */
const CONVERSATIONS_PATH = '/sla-management/conversations';

export interface AskConversationPanelProps {
  ask: StockAsk;
  conversation: AskConversation | undefined;
  loading: boolean;
  /** CRM only: the link to that contact's chat history. */
  showOpenInConversations: boolean;
  onWholeDay: () => void;
  /** Saves the note; a rejection is the caller's to report, "Saved" shows only after it resolves. */
  onNote: (askId: string, note: string) => Promise<unknown> | void;
  onDone: (askId: string) => void;
  onReopen: (askId: string) => void;
  pending?: boolean;
}

/**
 * The body of the opened card (portal Drawer, CRM Sheet): who and when, the Asked / Answered
 * block, the messages around the ask, an explicit-save Note and the Done / Reopen foot. Nothing
 * technical: no turn ids, parser output or delivery status. Presentational: the mount fetches
 * the conversation and owns the drawer.
 */
export function AskConversationPanel({
  ask,
  conversation,
  loading,
  showOpenInConversations,
  onWholeDay,
  onNote,
  onDone,
  onReopen,
  pending = false,
}: AskConversationPanelProps) {
  const [note, setNote] = useState(ask.note ?? '');
  const [savedAt, setSavedAt] = useState<Date | null>(null);
  const [saving, setSaving] = useState(false);
  const [flash, setFlash] = useState(false);
  const taggedRef = useRef<HTMLDivElement | null>(null);
  const flashTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => {
    if (flashTimer.current) clearTimeout(flashTimer.current);
  }, []);

  const isDone = ask.state === 'done';
  const messages = conversation?.messages ?? [];
  const askMessageId = conversation?.ask_message_id ?? null;

  const jump = () => {
    taggedRef.current?.scrollIntoView({ block: 'center', behavior: 'smooth' });
    setFlash(true);
    if (flashTimer.current) clearTimeout(flashTimer.current);
    flashTimer.current = setTimeout(() => setFlash(false), 1800);
  };

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

  let lastDay = '';
  const href = conversation?.contact_id
    ? `${CONVERSATIONS_PATH}?contact=${encodeURIComponent(conversation.contact_id)}`
    : CONVERSATIONS_PATH;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-3">
        <header className="space-y-0.5">
          <p className="text-base">
            <span className="font-semibold">{ask.customer_name || ask.contact_name || '-'}</span>
            {ask.customer_name && ask.contact_name ? (
              <span className="text-sm text-muted-foreground"> {ask.contact_name}</span>
            ) : null}
          </p>
          <p className="text-xs text-muted-foreground">
            {formatDateTimeInMalaysia(ask.created_at)}
            {ask.agent_code ? ` · ${ask.agent_code}` : ''}
          </p>
        </header>

        <div className="space-y-1 rounded-lg border bg-muted/40 px-3 py-2.5">
          <p className="text-sm break-words">
            <span className="text-muted-foreground">Asked: </span>
            {askProductText(ask)}
          </p>
          <p className="text-sm break-words">
            <span className="text-muted-foreground">Answered: </span>
            {askAnswerText(ask)}
          </p>
          <Button type="button" variant="ghost" size="sm" className="-ml-2" onClick={jump} disabled={askMessageId == null}>
            Jump to message
          </Button>
        </div>

        <section className="space-y-2" aria-label="Conversation">
          <h3 className="text-sm font-semibold">Conversation</h3>
          {loading && !conversation ? (
            <div className="space-y-2" role="status" aria-label="Loading">
              <Skeleton className="h-9 w-2/3" />
              <Skeleton className="ml-auto h-9 w-2/3" />
              <Skeleton className="h-9 w-1/2" />
            </div>
          ) : messages.length === 0 ? (
            <p className="text-sm text-muted-foreground">No messages around this ask.</p>
          ) : (
            <div className="space-y-2">
              {messages.map((m) => {
                const day = formatDateInMalaysia(utcMs(m.at));
                const separator = day !== lastDay;
                lastDay = day;
                const isAsk = m.id === askMessageId;
                return (
                  <div key={m.id} className="space-y-2">
                    {separator ? (
                      <p className="text-center text-xs text-muted-foreground">{formatChatDayPillMalaysia(utcMs(m.at))}</p>
                    ) : null}
                    <div
                      ref={isAsk ? taggedRef : undefined}
                      data-testid="conversation-bubble"
                      data-direction={m.direction}
                      className={cn(
                        'max-w-[85%] rounded-lg px-3 py-2 text-sm break-words whitespace-pre-wrap',
                        m.direction === 'in' ? 'mr-auto bg-muted' : 'ml-auto bg-primary/10',
                        isAsk && flash && 'ask-bubble-flash ring-2 ring-primary',
                      )}
                    >
                      {isAsk ? <p className="mb-0.5 text-xs font-medium text-primary">This ask</p> : null}
                      <p>{m.text}</p>
                      <p className="mt-0.5 text-right text-[0.6875rem] text-muted-foreground">
                        {formatTimeShortMalaysia(utcMs(m.at))}
                      </p>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
          <div className="flex flex-wrap items-center gap-2">
            <Button type="button" variant="outline" size="sm" onClick={onWholeDay}>
              Show the whole day
            </Button>
            {showOpenInConversations ? (
              <Link href={href} className="text-sm text-primary underline-offset-4 hover:underline">
                Open in Conversations
              </Link>
            ) : null}
          </div>
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
              <span className="text-xs text-muted-foreground">Saved {formatTimeShortMalaysia(savedAt)}</span>
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
