/**
 * Live conversation events - transport (UAC AC-K1 / AC-K2, PLAN slice S4.2).
 *
 * Contract: documentation/plans/sla/conversation-intervention-tickets-acceptance-criteria.md
 * Plan:     documentation/plans/sla/PLAN-conversation-intervention-tickets.md (S4.2)
 *
 * ---------------------------------------------------------------------------
 * BACKEND CONTRACT (as shipped)
 * ---------------------------------------------------------------------------
 * GET /api/v1/sla-management/conversation-events/stream?contacts=<id>[,<id>]
 *   - `text/event-stream`, chunked. Max 25 contacts; the backend drops any the
 *     caller has no ticket standing for, silently.
 *   - `event: ready` on connect (the cue to refetch), then `event: <type>` with
 *     a JSON `data:` line, plus a `: keep-alive` comment roughly every 25s.
 *   - Types: `message` | `ticket_created` | `ticket_updated`. A NOTE is poked as
 *     `message` (ticket_comment_service publishes EVENT_MESSAGE), so a `message`
 *     event has to refresh the notes as well as the thread.
 *   - Payload, five keys, never any content:
 *     `{type, contact_id, user_id, entity_id, ts}`. `contact_id` is the
 *     Respond.io contact id (`respond_contacts.respond_io_id`), NOT the internal
 *     UUID.
 *   - Stateless: no Last-Event-ID, no replay. A reconnect just resubscribes and
 *     the gap is covered by the refetch on `ready` plus the surface's slow poll.
 *
 * ---------------------------------------------------------------------------
 * WHY fetch + ReadableStream AND NOT `EventSource`
 * ---------------------------------------------------------------------------
 * The route authenticates with `Depends(get_current_user)`, whose token comes
 * from `oauth2_scheme` or `extract_token_from_request` - and that helper reads
 * the `Authorization: Bearer` header ONLY (it returns None for cookies, and no
 * route accepts a `?token=` query param; the NextAuth cookie is an encrypted JWE
 * FastAPI cannot read anyway). `EventSource` cannot set request headers, so it
 * would hit this endpoint unauthenticated and take a 401 forever.
 *
 * Reading the stream through `apiFetch` therefore is not a workaround, it is the
 * only way to reach the endpoint AND it keeps the surface on the normal layering:
 * the cached/deduped JWT mint, the base-URL rewriting and the session-revoked
 * interceptor all come for free instead of being re-implemented on a raw
 * `EventSource` URL. The cost is that we parse the wire format ourselves, which
 * is ~30 lines and is unit-tested below the hook.
 */

import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

const STREAM_URL = '/api/v1/sla-management/conversation-events/stream';

/** The backend caps `?contacts=` at this; sending more is silently truncated. */
export const MAX_STREAM_CONTACTS = 25;

export type ConversationEventType = 'message' | 'ticket_created' | 'ticket_updated';

/** One poke. Content-free by contract: the subscriber refetches over REST. */
export interface ConversationEvent {
  type: string;
  /** Respond.io contact id (`respond_io_id`), never the internal UUID. */
  contact_id: string | null;
  user_id: string | null;
  entity_id: string | null;
  ts: string | null;
}

export interface ConversationEventStreamHandlers {
  /** Fired once per successful connect - the cue to refetch (a gap may exist). */
  onReady?: () => void;
  onEvent?: (event: ConversationEvent) => void;
}

/** One decoded SSE frame. `null` for a frame that carries nothing usable. */
export interface ParsedEventFrame {
  event: string;
  data: string;
}

/**
 * Decode one SSE frame (the text between two blank lines).
 *
 * Comment lines (`: keep-alive`) and frames with no `data:` yield null - a
 * heartbeat is not an event and must not wake a subscriber up.
 */
export function parseEventStreamFrame(raw: string): ParsedEventFrame | null {
  let event = 'message';
  const dataLines: string[] = [];
  for (const line of raw.split('\n')) {
    if (!line || line.startsWith(':')) continue;
    const separator = line.indexOf(':');
    const field = separator === -1 ? line : line.slice(0, separator);
    // "field: value" - exactly one optional leading space is part of the format.
    let value = separator === -1 ? '' : line.slice(separator + 1);
    if (value.startsWith(' ')) value = value.slice(1);
    if (field === 'event') event = value;
    else if (field === 'data') dataLines.push(value);
  }
  if (dataLines.length === 0) return null;
  return { event, data: dataLines.join('\n') };
}

/** Coerce a decoded `data:` line into the five-key envelope, or null. */
export function toConversationEvent(frame: ParsedEventFrame): ConversationEvent | null {
  let payload: Record<string, unknown>;
  try {
    payload = JSON.parse(frame.data) as Record<string, unknown>;
  } catch {
    // A malformed frame is a transport hiccup, not a reason to drop the stream.
    return null;
  }
  if (!payload || typeof payload !== 'object') return null;
  const type = String(payload.type ?? frame.event ?? '').trim();
  if (!type) return null;
  const str = (value: unknown) => (value == null ? null : String(value));
  return {
    type,
    contact_id: str(payload.contact_id),
    user_id: str(payload.user_id),
    entity_id: str(payload.entity_id),
    ts: str(payload.ts),
  };
}

/**
 * Open the stream and pump frames until it ends or `signal` aborts.
 *
 * Resolves when the server closed the stream (the caller decides whether to
 * reconnect); rejects when the connection could not be established or died
 * mid-flight. An abort resolves rather than rejecting - the caller asked.
 */
export async function openConversationEventStream(
  contacts: string[],
  handlers: ConversationEventStreamHandlers,
  signal: AbortSignal,
): Promise<void> {
  const wanted = contacts
    .map((id) => String(id ?? '').trim())
    .filter(Boolean)
    .slice(0, MAX_STREAM_CONTACTS);
  const query = wanted.length ? `?contacts=${encodeURIComponent(wanted.join(','))}` : '';

  const response = await apiFetch(`${STREAM_URL}${query}`, {
    signal,
    cache: 'no-store',
    headers: { Accept: 'text/event-stream' },
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Live updates are unavailable'));
  }
  const body = response.body;
  if (!body || typeof body.getReader !== 'function') {
    // No streaming body (an old browser, or a proxy that buffered it away).
    throw new Error('Live updates are unavailable on this connection');
  }

  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  // The stream is only ever closed by the caller's abort, so release the lock
  // from here rather than trusting the loop to fall out of read().
  const onAbort = () => {
    void reader.cancel().catch(() => undefined);
  };
  signal.addEventListener('abort', onAbort, { once: true });

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) return;
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n');
      let boundary = buffer.indexOf('\n\n');
      while (boundary !== -1) {
        const raw = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const frame = parseEventStreamFrame(raw);
        if (frame) {
          if (frame.event === 'ready') {
            handlers.onReady?.();
          } else {
            const event = toConversationEvent(frame);
            if (event) handlers.onEvent?.(event);
          }
        }
        boundary = buffer.indexOf('\n\n');
      }
    }
  } catch (error) {
    // An abort is the caller closing the drawer, not a failure to report.
    if (signal.aborted) return;
    throw error;
  } finally {
    signal.removeEventListener('abort', onAbort);
  }
}
