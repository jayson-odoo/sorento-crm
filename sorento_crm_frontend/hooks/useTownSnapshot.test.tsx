import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

/**
 * SORENTO-TOWN Phase 1: `useTownSnapshot` polls every 60 s only while the tab is visible, sends the
 * last ETag back, and keeps the previous snapshot on a 304 (plan "Phase 1 screen").
 *
 * Assumed API (the plan names only the file): `useTownSnapshot(options?: { mode?: 'wallboard' })`
 * returns `{ snapshot, error, isLoading }`; it calls `getSnapshot(etag?, mode?)` from
 * `@/services/townService`.
 */
const getSnapshot = vi.fn();
vi.mock('@/services/townService', () => ({ getSnapshot: (...a: unknown[]) => getSnapshot(...a) }));

import { useTownSnapshot } from './useTownSnapshot';

const FIRST = { schema: 1, today: { invoice_count: 1 } };
const SECOND = { schema: 1, today: { invoice_count: 2 } };

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return React.createElement(QueryClientProvider, { client }, children);
}

function setVisibility(state: 'visible' | 'hidden') {
  Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => state });
  document.dispatchEvent(new Event('visibilitychange'));
}

async function advance(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

beforeEach(() => {
  vi.useFakeTimers();
  getSnapshot.mockReset();
  setVisibility('visible');
});

afterEach(() => {
  vi.useRealTimers();
  setVisibility('visible');
});

describe('useTownSnapshot', () => {
  it('fetches once on mount and exposes the snapshot', async () => {
    getSnapshot.mockResolvedValue({ notModified: false, snapshot: FIRST, etag: '"v1-full"' });
    const { result } = renderHook(() => useTownSnapshot(), { wrapper });
    await advance(10);
    expect(getSnapshot).toHaveBeenCalledTimes(1);
    expect(result.current.snapshot).toEqual(FIRST);
  });

  it('polls every 60 seconds while the tab is visible, sending the last ETag', async () => {
    getSnapshot
      .mockResolvedValueOnce({ notModified: false, snapshot: FIRST, etag: '"v1-full"' })
      .mockResolvedValue({ notModified: false, snapshot: SECOND, etag: '"v2-full"' });
    const { result } = renderHook(() => useTownSnapshot(), { wrapper });
    await advance(10);
    await advance(59_000);
    expect(getSnapshot).toHaveBeenCalledTimes(1); // not before 60 s
    await advance(1_500);
    expect(getSnapshot).toHaveBeenCalledTimes(2);
    expect(getSnapshot.mock.calls[1][0]).toBe('"v1-full"');
    expect(result.current.snapshot).toEqual(SECOND);
    await advance(60_000);
    expect(getSnapshot).toHaveBeenCalledTimes(3);
    expect(getSnapshot.mock.calls[2][0]).toBe('"v2-full"');
  });

  it('does not poll while the tab is hidden, and polls again once visible', async () => {
    getSnapshot.mockResolvedValue({ notModified: false, snapshot: FIRST, etag: '"v1-full"' });
    renderHook(() => useTownSnapshot(), { wrapper });
    await advance(10);
    expect(getSnapshot).toHaveBeenCalledTimes(1);
    setVisibility('hidden');
    await advance(5 * 60_000);
    expect(getSnapshot).toHaveBeenCalledTimes(1);
    setVisibility('visible');
    await advance(61_000);
    expect(getSnapshot.mock.calls.length).toBeGreaterThanOrEqual(2);
  });

  it('keeps the previous snapshot when the server answers notModified', async () => {
    getSnapshot
      .mockResolvedValueOnce({ notModified: false, snapshot: FIRST, etag: '"v1-full"' })
      .mockResolvedValue({ notModified: true });
    const { result } = renderHook(() => useTownSnapshot(), { wrapper });
    await advance(10);
    await advance(61_000);
    expect(getSnapshot.mock.calls.length).toBeGreaterThanOrEqual(2);
    expect(result.current.snapshot).toEqual(FIRST);
    await advance(60_000);
    expect(getSnapshot.mock.calls[2][0]).toBe('"v1-full"'); // the etag is kept too
  });

  it('asks for the wallboard variant when told to', async () => {
    getSnapshot.mockResolvedValue({ notModified: false, snapshot: FIRST, etag: '"v1-full-wb"' });
    renderHook(() => useTownSnapshot({ mode: 'wallboard' }), { wrapper });
    await advance(10);
    expect(getSnapshot.mock.calls[0][1]).toBe('wallboard');
  });

  it('stops polling after unmount', async () => {
    getSnapshot.mockResolvedValue({ notModified: false, snapshot: FIRST, etag: '"v1-full"' });
    const { unmount } = renderHook(() => useTownSnapshot(), { wrapper });
    await advance(10);
    unmount();
    await advance(5 * 60_000);
    expect(getSnapshot).toHaveBeenCalledTimes(1);
  });
});
