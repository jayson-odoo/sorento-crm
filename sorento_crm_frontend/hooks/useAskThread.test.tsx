/**
 * ASKS-UX item 3 (AC-AU12): the opened ask's thread source. What is pinned: the tail is the page
 * read with no cursor, nothing is read while no ask is open, the loaders are keyed on the ask,
 * and a failed POLL on a loaded tail is not an error (the thread must not blank and lose the
 * reader's place); only a first read that left nothing to show is.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useAskThread, type AskThreadService } from './useAskThread';

const PAGE = { items: [{ messageId: 1, traffic: 'incoming', message: { type: 'text', text: 'hi' }, status: [] }], has_more_older: false, has_more_newer: false, oldest_message_id: '1', newest_message_id: '1' };

let client: QueryClient;
const service: AskThreadService = { getPage: vi.fn(), search: vi.fn() };
const wrapper = ({ children }: { children: React.ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;

beforeEach(() => {
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  vi.mocked(service.getPage).mockReset().mockResolvedValue(PAGE as never);
  vi.mocked(service.search).mockReset().mockResolvedValue([]);
});

describe('useAskThread', () => {
  it('reads the tail with no cursor for the open ask, and nothing while no ask is open', async () => {
    const { result, rerender } = renderHook(({ id }: { id: string | null }) => useAskThread(id, service, 'test'), {
      wrapper,
      initialProps: { id: null as string | null },
    });
    expect(service.getPage).not.toHaveBeenCalled();
    expect(result.current.liveItems).toEqual([]);
    rerender({ id: 'ask-1' });
    await waitFor(() => expect(result.current.liveItems).toHaveLength(1));
    expect(service.getPage).toHaveBeenCalledWith('ask-1', { limit: 50 });
    await result.current.loadPage({ before: '1', limit: 50 });
    expect(service.getPage).toHaveBeenLastCalledWith('ask-1', { before: '1', limit: 50 });
    await result.current.searchMessages('hi');
    expect(service.search).toHaveBeenCalledWith('ask-1', 'hi');
  });

  it('reports the error only when the first read left nothing to show; a failed poll keeps the tail', async () => {
    // Persistent rejections: the hook retries once before it reports.
    vi.mocked(service.getPage).mockRejectedValue(new Error('Server down'));
    const { result } = renderHook(() => useAskThread('ask-1', service, 'test'), { wrapper });
    await waitFor(() => expect(result.current.error).toBe('Server down'));
    expect(result.current.liveItems).toEqual([]);

    vi.mocked(service.getPage).mockResolvedValue(PAGE as never);
    await act(async () => {
      await client.refetchQueries({ queryKey: ['test', 'ask-thread-tail', 'ask-1'] });
    });
    await waitFor(() => expect(result.current.liveItems).toHaveLength(1));
    expect(result.current.error).toBeNull();

    vi.mocked(service.getPage).mockRejectedValue(new Error('Poll failed'));
    await act(async () => {
      await client.refetchQueries({ queryKey: ['test', 'ask-thread-tail', 'ask-1'] });
    });
    expect(result.current.liveItems).toHaveLength(1); // still on screen
    expect(result.current.error).toBeNull(); // not blanked
  });
});
