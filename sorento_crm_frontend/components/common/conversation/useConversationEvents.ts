'use client';

import { useEffect, useMemo, useRef, useState } from 'react';

import {
  openConversationEventStream,
  type ConversationEvent,
} from '@/services/conversationEventsService';

/** First reconnect wait. Doubles per failure. */
export const RECONNECT_MIN_MS = 1_000;
/** Ceiling on the reconnect wait - a dead backend must not be hammered. */
export const RECONNECT_MAX_MS = 30_000;

export interface UseConversationEventsOptions {
  /**
   * Respond.io contact ids (`respond_io_id`) this surface has OPEN. Empty or all
   * null means no stream at all (AC-K2: liveness costs nothing when nothing is
   * open). Unstable array identity is fine - the subscription is keyed on the
   * sorted contents, not the reference.
   */
  contactIds: (string | null | undefined)[];
  /** False closes the stream (drawer shut, pane unmounted, page hidden). */
  enabled?: boolean;
  /**
   * Called for every poke naming one of `contactIds`. Refetch here - the event
   * carries no content by design, which is what makes a replayed or duplicated
   * event a no-op on screen (AC-K4).
   */
  onEvent?: (event: ConversationEvent) => void;
  /**
   * Called on each successful connect. A reconnect may have missed events, so
   * this is a refetch cue as much as `onEvent` is.
   */
  onReady?: () => void;
}

export interface ConversationEventsState {
  /**
   * True between a `ready` frame and the stream dropping. Surfaces relax their
   * poll while it is true and fall back to the fast poll while it is false, so
   * a dead stream degrades to exactly the behaviour that shipped before it.
   */
  connected: boolean;
}

/** 1s, 2s, 4s ... capped. */
export function reconnectDelayMs(attempt: number): number {
  return Math.min(RECONNECT_MIN_MS * 2 ** Math.max(0, attempt), RECONNECT_MAX_MS);
}

/**
 * Subscribe an open conversation surface to the live event stream (AC-K1).
 *
 * ONE stream per surface, opened only while something is actually open and
 * closed on unmount or when the contact changes (AC-K2). Every frame is a poke:
 * the hook hands it to `onEvent`, the caller refetches through the normal
 * permissioned REST endpoints, and nothing on the wire is ever rendered.
 *
 * Transport is fetch + ReadableStream rather than `EventSource`, because the
 * endpoint authenticates on the `Authorization: Bearer` header and `EventSource`
 * cannot set one - see `services/conversationEventsService.ts` for the full
 * reasoning.
 */
export function useConversationEvents({
  contactIds,
  enabled = true,
  onEvent,
  onReady,
}: UseConversationEventsOptions): ConversationEventsState {
  const [connected, setConnected] = useState(false);

  // Sorted + deduped, so a re-render that rebuilds the array does not reopen
  // the stream. This string IS the effect's dependency.
  const contactKey = useMemo(() => {
    const unique = new Set(
      contactIds.map((id) => String(id ?? '').trim()).filter(Boolean),
    );
    return Array.from(unique).sort().join(',');
  }, [contactIds]);

  // Callbacks live in refs: a caller that passes an inline arrow (all of them
  // do) would otherwise tear the stream down on every render.
  const onEventRef = useRef(onEvent);
  const onReadyRef = useRef(onReady);
  useEffect(() => {
    onEventRef.current = onEvent;
    onReadyRef.current = onReady;
  }, [onEvent, onReady]);

  useEffect(() => {
    if (!enabled || !contactKey) {
      setConnected(false);
      return;
    }
    const contacts = contactKey.split(',');
    const wanted = new Set(contacts);
    const controller = new AbortController();
    let cancelled = false;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    // Cleanup during a backoff wait must wake the sleeper, or the suspended
    // run() (and every closure it holds) outlives the drawer that opened it.
    let wakeRetry: (() => void) | null = null;

    const run = async () => {
      let attempt = 0;
      while (!cancelled) {
        try {
          await openConversationEventStream(
            contacts,
            {
              onReady: () => {
                if (cancelled) return;
                // A live connection resets the backoff: the next drop starts
                // from 1s again rather than inheriting an old outage's ceiling.
                attempt = 0;
                setConnected(true);
                onReadyRef.current?.();
              },
              onEvent: (event) => {
                if (cancelled) return;
                // The backend filters server-side too; this is the client half,
                // and it is what keeps a user-keyed worklist poke for ANOTHER
                // contact from refetching this thread.
                if (!event.contact_id || !wanted.has(event.contact_id)) return;
                onEventRef.current?.(event);
              },
            },
            controller.signal,
          );
        } catch {
          // Any transport failure is the same story: fall back to polling and
          // try again later. Nothing to report to the user - the surface still
          // works, just less promptly.
        }
        if (cancelled) return;
        setConnected(false);
        const delay = reconnectDelayMs(attempt);
        attempt += 1;
        await new Promise<void>((resolve) => {
          wakeRetry = resolve;
          retryTimer = setTimeout(resolve, delay);
        });
        wakeRetry = null;
      }
    };

    void run();

    return () => {
      cancelled = true;
      if (retryTimer) clearTimeout(retryTimer);
      wakeRetry?.();
      controller.abort();
      setConnected(false);
    };
  }, [contactKey, enabled]);

  return { connected };
}
