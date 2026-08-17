import { beforeEach, describe, expect, it, vi } from 'vitest';

/**
 * The live-conversation SSE transport (UAC AC-K1, PLAN S4.2).
 *
 * The wire format is parsed here rather than by `EventSource` (the endpoint
 * authenticates on a Bearer header, which EventSource cannot set), so the frame
 * decoding and the chunk boundaries are ours to pin.
 */
const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));
vi.mock('@/lib/api-client', () => ({
  extractApiError: vi.fn().mockResolvedValue('Live updates are unavailable'),
}));

import {
  openConversationEventStream,
  parseEventStreamFrame,
  toConversationEvent,
  type ConversationEvent,
} from './conversationEventsService';

/** A Response-alike whose body yields `chunks` and then ends. */
function streamResponse(chunks: string[], { ok = true } = {}) {
  const encoder = new TextEncoder();
  let index = 0;
  return {
    ok,
    status: ok ? 200 : 401,
    body: {
      getReader: () => ({
        read: async () =>
          index < chunks.length
            ? { done: false, value: encoder.encode(chunks[index++]) }
            : { done: true, value: undefined },
        cancel: async () => undefined,
      }),
    },
  };
}

function frame(type: string, payload: Record<string, unknown>): string {
  return `event: ${type}\ndata: ${JSON.stringify(payload)}\n\n`;
}

beforeEach(() => {
  apiFetch.mockReset();
});

describe('parseEventStreamFrame', () => {
  it('reads the event name and the data line', () => {
    expect(parseEventStreamFrame('event: message\ndata: {"a":1}')).toEqual({
      event: 'message',
      data: '{"a":1}',
    });
  });

  it('defaults the event name to "message" when the frame omits it', () => {
    expect(parseEventStreamFrame('data: {"a":1}')?.event).toBe('message');
  });

  it('ignores a keep-alive comment - a heartbeat is not an event', () => {
    expect(parseEventStreamFrame(': keep-alive')).toBeNull();
  });

  it('joins multi-line data with newlines', () => {
    expect(parseEventStreamFrame('data: one\ndata: two')?.data).toBe('one\ntwo');
  });
});

describe('toConversationEvent', () => {
  it('normalises the five-key envelope', () => {
    const event = toConversationEvent({
      event: 'message',
      data: '{"type":"message","contact_id":10025904,"user_id":null,"entity_id":null,"ts":"2026-08-15T01:02:03Z"}',
    });
    expect(event).toEqual({
      type: 'message',
      contact_id: '10025904',
      user_id: null,
      entity_id: null,
      ts: '2026-08-15T01:02:03Z',
    });
  });

  it('drops an undecodable payload instead of throwing', () => {
    expect(toConversationEvent({ event: 'message', data: 'not json' })).toBeNull();
  });
});

describe('openConversationEventStream', () => {
  it('passes the contacts filter and emits ready then events', async () => {
    apiFetch.mockResolvedValue(
      streamResponse([
        frame('ready', { type: 'ready', contacts: ['10025904'] }),
        frame('message', { type: 'message', contact_id: '10025904', ts: 'x' }),
      ]),
    );
    const onReady = vi.fn();
    const onEvent = vi.fn();

    await openConversationEventStream(
      ['10025904', '10025905'],
      { onReady, onEvent },
      new AbortController().signal,
    );

    expect(apiFetch).toHaveBeenCalledWith(
      '/api/v1/sla-management/conversation-events/stream?contacts=10025904%2C10025905',
      expect.objectContaining({ cache: 'no-store' }),
    );
    expect(onReady).toHaveBeenCalledTimes(1);
    expect(onEvent).toHaveBeenCalledTimes(1);
    expect((onEvent.mock.calls[0][0] as ConversationEvent).contact_id).toBe('10025904');
  });

  it('reassembles a frame split across two chunks', async () => {
    const whole = frame('ticket_updated', {
      type: 'ticket_updated',
      contact_id: '1',
      entity_id: 'tkt-1',
    });
    apiFetch.mockResolvedValue(streamResponse([whole.slice(0, 20), whole.slice(20)]));
    const onEvent = vi.fn();

    await openConversationEventStream(['1'], { onEvent }, new AbortController().signal);

    expect(onEvent).toHaveBeenCalledTimes(1);
    expect((onEvent.mock.calls[0][0] as ConversationEvent).type).toBe('ticket_updated');
  });

  it('a keep-alive comment wakes nobody', async () => {
    apiFetch.mockResolvedValue(streamResponse([': keep-alive\n\n']));
    const onEvent = vi.fn();
    const onReady = vi.fn();

    await openConversationEventStream(['1'], { onEvent, onReady }, new AbortController().signal);

    expect(onEvent).not.toHaveBeenCalled();
    expect(onReady).not.toHaveBeenCalled();
  });

  it('caps the contact list at the backend maximum', async () => {
    apiFetch.mockResolvedValue(streamResponse([]));
    const many = Array.from({ length: 40 }, (_, i) => String(1000 + i));

    await openConversationEventStream(many, {}, new AbortController().signal);

    const url = String(apiFetch.mock.calls[0][0]);
    expect(decodeURIComponent(url.split('contacts=')[1]).split(',')).toHaveLength(25);
  });

  it('throws when the stream cannot be opened', async () => {
    apiFetch.mockResolvedValue(streamResponse([], { ok: false }));

    await expect(
      openConversationEventStream(['1'], {}, new AbortController().signal),
    ).rejects.toThrow('Live updates are unavailable');
  });

  it('an abort mid-read resolves instead of reporting a failure', async () => {
    const controller = new AbortController();
    apiFetch.mockResolvedValue({
      ok: true,
      body: {
        getReader: () => ({
          read: async () => {
            controller.abort();
            throw new DOMException('aborted', 'AbortError');
          },
          cancel: async () => undefined,
        }),
      },
    });

    await expect(
      openConversationEventStream(['1'], {}, controller.signal),
    ).resolves.toBeUndefined();
  });
});
