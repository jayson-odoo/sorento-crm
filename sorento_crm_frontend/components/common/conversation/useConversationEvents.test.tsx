import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

/**
 * The live-thread subscriber (UAC AC-K1 / AC-K2).
 *
 * The transport is stubbed so this is about the subscription lifecycle: one
 * stream while something is open, none while nothing is, contact filtering,
 * reconnect with backoff, and a clean teardown.
 */
interface FakeStream {
  contacts: string[];
  ready: () => void;
  emit: (event: Record<string, unknown>) => void;
  /** Ends the stream as the server closing it (the hook then reconnects). */
  close: () => void;
  /** Ends it as a transport failure. */
  fail: (error?: Error) => void;
  aborted: boolean;
}

const streams: FakeStream[] = [];

const openConversationEventStream = vi.fn(
  (
    contacts: string[],
    handlers: { onReady?: () => void; onEvent?: (e: unknown) => void },
    signal: AbortSignal,
  ) =>
    new Promise<void>((resolve, reject) => {
      const stream: FakeStream = {
        contacts,
        aborted: false,
        ready: () => handlers.onReady?.(),
        emit: (event) => handlers.onEvent?.(event),
        close: () => resolve(),
        fail: (error) => reject(error ?? new Error('stream died')),
      };
      signal.addEventListener('abort', () => {
        stream.aborted = true;
        resolve();
      });
      streams.push(stream);
    }),
);

vi.mock('@/services/conversationEventsService', () => ({
  MAX_STREAM_CONTACTS: 25,
  openConversationEventStream: (...a: unknown[]) =>
    (openConversationEventStream as unknown as (...args: unknown[]) => Promise<void>)(...a),
}));

import { reconnectDelayMs, useConversationEvents } from './useConversationEvents';

/** The stream the hook currently holds open. */
const latest = () => streams[streams.length - 1];

beforeEach(() => {
  streams.length = 0;
  openConversationEventStream.mockClear();
  vi.useFakeTimers({ shouldAdvanceTime: true });
});

afterEach(() => {
  vi.useRealTimers();
});

describe('reconnectDelayMs', () => {
  it('doubles from 1s and stops at 30s', () => {
    expect(reconnectDelayMs(0)).toBe(1_000);
    expect(reconnectDelayMs(1)).toBe(2_000);
    expect(reconnectDelayMs(4)).toBe(16_000);
    expect(reconnectDelayMs(5)).toBe(30_000);
    expect(reconnectDelayMs(20)).toBe(30_000);
  });
});

describe('useConversationEvents', () => {
  it('opens ONE stream for the given contacts and reports connected on ready', async () => {
    const { result } = renderHook(() =>
      useConversationEvents({ contactIds: ['10025904'], onEvent: vi.fn() }),
    );

    await waitFor(() => expect(streams).toHaveLength(1));
    expect(latest().contacts).toEqual(['10025904']);
    expect(result.current.connected).toBe(false);

    act(() => latest().ready());
    await waitFor(() => expect(result.current.connected).toBe(true));
  });

  it('holds no stream while nothing is open (AC-K2)', async () => {
    const { rerender } = renderHook(
      ({ enabled }: { enabled: boolean }) =>
        useConversationEvents({ contactIds: ['10025904'], enabled, onEvent: vi.fn() }),
      { initialProps: { enabled: false } },
    );
    await act(async () => undefined);
    expect(streams).toHaveLength(0);

    rerender({ enabled: true });
    await waitFor(() => expect(streams).toHaveLength(1));

    rerender({ enabled: false });
    await waitFor(() => expect(streams[0].aborted).toBe(true));
  });

  it('holds no stream when there is no contact to subscribe to', async () => {
    renderHook(() => useConversationEvents({ contactIds: [null, undefined, ''], onEvent: vi.fn() }));
    await act(async () => undefined);
    expect(streams).toHaveLength(0);
  });

  it('forwards only the pokes naming a subscribed contact', async () => {
    const onEvent = vi.fn();
    renderHook(() => useConversationEvents({ contactIds: ['10025904'], onEvent }));
    await waitFor(() => expect(streams).toHaveLength(1));

    act(() => {
      latest().emit({ type: 'message', contact_id: '10025904' });
      latest().emit({ type: 'message', contact_id: '99999999' });
      latest().emit({ type: 'ticket_updated', contact_id: null, user_id: 'u1' });
    });

    expect(onEvent).toHaveBeenCalledTimes(1);
    expect(onEvent).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'message', contact_id: '10025904' }),
    );
  });

  it('does not reopen the stream when the callback identity changes', async () => {
    const { rerender } = renderHook(() =>
      useConversationEvents({ contactIds: ['10025904'], onEvent: () => undefined }),
    );
    await waitFor(() => expect(streams).toHaveLength(1));

    rerender();
    rerender();
    await act(async () => undefined);

    expect(streams).toHaveLength(1);
  });

  it('reconnects with backoff after the stream drops, and clears connected meanwhile', async () => {
    const { result } = renderHook(() =>
      useConversationEvents({ contactIds: ['10025904'], onEvent: vi.fn() }),
    );
    await waitFor(() => expect(streams).toHaveLength(1));
    act(() => latest().ready());
    await waitFor(() => expect(result.current.connected).toBe(true));

    await act(async () => {
      latest().fail();
    });
    await waitFor(() => expect(result.current.connected).toBe(false));
    // Still waiting out the first 1s backoff.
    expect(streams).toHaveLength(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1_000);
    });
    await waitFor(() => expect(streams).toHaveLength(2));
  });

  it('a contact change closes the old stream and opens one for the new contact', async () => {
    const { rerender } = renderHook(
      ({ id }: { id: string }) => useConversationEvents({ contactIds: [id], onEvent: vi.fn() }),
      { initialProps: { id: '10025904' } },
    );
    await waitFor(() => expect(streams).toHaveLength(1));

    rerender({ id: '10025905' });

    await waitFor(() => expect(streams).toHaveLength(2));
    expect(streams[0].aborted).toBe(true);
    expect(streams[1].contacts).toEqual(['10025905']);
  });

  it('closes the stream on unmount', async () => {
    const { unmount } = renderHook(() =>
      useConversationEvents({ contactIds: ['10025904'], onEvent: vi.fn() }),
    );
    await waitFor(() => expect(streams).toHaveLength(1));

    unmount();

    await waitFor(() => expect(streams[0].aborted).toBe(true));
  });
});
