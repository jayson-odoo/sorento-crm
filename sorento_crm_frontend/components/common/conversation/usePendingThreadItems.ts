'use client';

import { useCallback, useRef, useState } from 'react';
import type { RespondMessageRenderable } from '@/lib/respondIoChatRender';

/** What the composer is about to send, as the pending bubbles should show it. */
export interface PendingSendInput {
  text: string;
  files?: Array<{ name: string }>;
}

/**
 * A bubble for a message the composer has sent but the thread has not read
 * back yet (PLAN-optimistic-send AC-B1 / M6-01). No `messageId` (nothing to
 * dedupe on), a `pending` receipt so the list draws the "sending" clock, and a
 * `pendingKey` so the send that created it can take it down again.
 */
export type PendingThreadItem = RespondMessageRenderable & {
  source: 'pending';
  pendingKey: string;
};

/**
 * The optimistic-bubble half of a conversation thread, on its own.
 *
 * `useConversationThread` composes this for the scroll-back surfaces (the
 * intervention-ticket drawer, the Conversations inbox); a panel with no
 * scroll-back - Complaint / Stock Inquiry / Purchase Request, which just
 * render a plain react-query list through `RespondChatList` - uses it
 * directly. Either way `RespondChatList` only ever needs `pendingItems`
 * merged into `items`; this is the ONE place the bubble's shape, its key
 * scheme and the attachment-placeholder text are decided, so a future surface
 * inherits the same optimistic send instead of writing its own.
 */
export function usePendingThreadItems() {
  const [pendingItems, setPendingItems] = useState<PendingThreadItem[]>([]);
  const pendingSeq = useRef(0);

  const addPending = useCallback((input: PendingSendInput) => {
    pendingSeq.current += 1;
    const pendingKey = `pending-${pendingSeq.current}`;
    const now = Date.now();
    const bubble = (text: string): PendingThreadItem => ({
      traffic: 'outgoing',
      message: { type: 'text', text },
      status: [{ value: 'pending', timestamp: now }],
      source: 'pending',
      pendingKey,
    });
    const next: PendingThreadItem[] = [];
    if (input.text.trim()) next.push(bubble(input.text.trim()));
    // The backend stores an attachment as "[kind] name"; the same placeholder
    // here means the swap to the real row does not change the bubble's words.
    for (const file of input.files ?? []) next.push(bubble(`[file] ${file.name}`));
    if (next.length) setPendingItems((current) => [...current, ...next]);
    return pendingKey;
  }, []);

  const removePending = useCallback((key: string) => {
    setPendingItems((current) =>
      current.some((item) => item.pendingKey === key)
        ? current.filter((item) => item.pendingKey !== key)
        : current,
    );
  }, []);

  /** Drop every pending bubble - a different conversation loading in the same
   *  mounted surface must not carry a stranger's in-flight send. */
  const clearPending = useCallback(() => setPendingItems([]), []);

  return { pendingItems, addPending, removePending, clearPending };
}
