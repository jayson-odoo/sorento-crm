'use client';

import { useCallback, useEffect, useState } from 'react';

import type { ReplyTarget } from '@/lib/respondIoChatRender';

/**
 * The message the next Reply answers (#1317), for a surface that pairs a
 * RespondChatList with a SharedConversationComposer. `resetKey` is the record
 * or contact on screen: another one never inherits the quote.
 */
export function useReplyTarget(resetKey: string | null | undefined) {
  const [replyTo, setReplyTo] = useState<ReplyTarget | null>(null);

  useEffect(() => {
    setReplyTo(null);
  }, [resetKey]);

  // Cancel (no argument) drops it; a completed send names the target it
  // carried, so a bubble picked while that send was in flight stays picked.
  const clearReplyTo = useCallback((sent?: ReplyTarget) => {
    setReplyTo((current) => (sent && current !== sent ? current : null));
  }, []);

  return { replyTo, startReply: setReplyTo, clearReplyTo };
}
