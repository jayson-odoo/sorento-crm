/**
 * EMBED-PAGE-PERF: the overview (a set of count queries over the embedding tables) is polled only while the Records
 * tab is showing in a visible browser tab, and a mutation's invalidation joins an overview fetch already in flight
 * instead of aborting it and starting a second one (an aborted fetch still runs its query on the server).
 */
import { act, renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider, focusManager } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const getOverview = vi.fn();
const recordsBackfill = vi.fn();
const embedMissing = vi.fn();
const saveEmbeddingSettings = vi.fn();

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('../services/embeddingsService', () => ({
  getOverview: () => getOverview(),
  recordsBackfill: (a: string) => recordsBackfill(a),
  embedMissing: () => embedMissing(),
  getLookupWords: vi.fn(),
  tryPhrase: vi.fn(),
}));

vi.mock('@/app/(protected)/user-management/settings/embeddings/services/embeddingSettingsService', () => ({
  getEmbeddingSettings: vi.fn(),
  saveEmbeddingSettings: (i: unknown) => saveEmbeddingSettings(i),
}));

import { useSaveEmbeddingSettings } from '@/app/(protected)/user-management/settings/embeddings/hooks/useEmbeddingSettings';
import { useEmbeddingsOverview, useEmbedMissing, useRecordsBackfill } from '../hooks/useEmbeddings';

function wrapper() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  }
  return Wrapper;
}

describe('useEmbeddingsOverview polling', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    getOverview.mockReset().mockResolvedValue({ ok: true });
    focusManager.setFocused(true);
  });
  afterEach(() => {
    focusManager.setFocused(undefined);
    vi.useRealTimers();
  });

  it('does not poll when the Records tab is not showing', async () => {
    renderHook(() => useEmbeddingsOverview({ poll: false }), { wrapper: wrapper() });
    await waitFor(() => expect(getOverview).toHaveBeenCalledTimes(1));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(95_000);
    });
    expect(getOverview).toHaveBeenCalledTimes(1);
  });

  it('polls every 30 s while the Records tab is showing', async () => {
    renderHook(() => useEmbeddingsOverview({ poll: true }), { wrapper: wrapper() });
    await waitFor(() => expect(getOverview).toHaveBeenCalledTimes(1));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_500);
    });
    expect(getOverview).toHaveBeenCalledTimes(2);
  });

  it('polls while a poll function says so (settings page: records search still moving)', async () => {
    getOverview.mockResolvedValueOnce({ moving: true }).mockResolvedValue({ moving: false });
    renderHook(() => useEmbeddingsOverview({ poll: (o) => !!(o as { moving?: boolean } | undefined)?.moving }), {
      wrapper: wrapper(),
    });
    await waitFor(() => expect(getOverview).toHaveBeenCalledTimes(1));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_500);
    });
    expect(getOverview).toHaveBeenCalledTimes(2);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(95_000);
    });
    expect(getOverview).toHaveBeenCalledTimes(2);
  });

  it('stops polling while the browser tab is hidden', async () => {
    renderHook(() => useEmbeddingsOverview({ poll: true }), { wrapper: wrapper() });
    await waitFor(() => expect(getOverview).toHaveBeenCalledTimes(1));
    act(() => focusManager.setFocused(false));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(95_000);
    });
    expect(getOverview).toHaveBeenCalledTimes(1);
  });
});

describe('one overview query at a time', () => {
  it.each([
    ['backfill start', () => useRecordsBackfill(), (m: { mutate: (v: { action: 'start' }) => void }) => m.mutate({ action: 'start' })],
    ['embed missing', () => useEmbedMissing(), (m: { mutate: () => void }) => m.mutate()],
    ['save settings', () => useSaveEmbeddingSettings(), (m: { mutate: (v: unknown) => void }) => m.mutate({})],
  ])('%s joins the overview fetch already in flight', async (_name, useMutationHook, run) => {
    let resolve: (v: unknown) => void = () => {};
    getOverview.mockReset().mockResolvedValueOnce({ n: 1 });
    recordsBackfill.mockReset().mockResolvedValue({ job_id: 'j' });
    embedMissing.mockReset().mockResolvedValue({ queued: true });
    saveEmbeddingSettings.mockReset().mockResolvedValue({});
    const { result } = renderHook(
      () => ({ overview: useEmbeddingsOverview(), mutation: useMutationHook() }),
      { wrapper: wrapper() },
    );
    await waitFor(() => expect(result.current.overview.data).toEqual({ n: 1 }));
    // A refresh is on the wire (the poll, or a focus refetch) when the mutation lands.
    getOverview.mockImplementation(() => new Promise((r) => (resolve = r)));
    act(() => void result.current.overview.refetch({ cancelRefetch: false }));
    await waitFor(() => expect(getOverview).toHaveBeenCalledTimes(2));
    act(() => run(result.current.mutation as never));
    await waitFor(() => expect(result.current.mutation.isSuccess).toBe(true));
    expect(getOverview).toHaveBeenCalledTimes(2);
    await act(async () => resolve({ n: 2 }));
    await waitFor(() => expect(result.current.overview.data).toEqual({ n: 2 }));
  });
});
