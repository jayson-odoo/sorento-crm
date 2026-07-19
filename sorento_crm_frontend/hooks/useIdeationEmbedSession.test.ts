import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// Mock the real feature service the hook now calls (Slice D — off the Phase-1 stub).
const getIdeationEmbedSession = vi.fn();
vi.mock('@/services/ideationService', () => ({
  getIdeationEmbedSession: (...args: unknown[]) => getIdeationEmbedSession(...args),
}));

import { useIdeationEmbedSession } from './useIdeationEmbedSession';

function Wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return React.createElement(QueryClientProvider, { client: qc }, children);
}

beforeEach(() => {
  getIdeationEmbedSession.mockReset();
});

describe('useIdeationEmbedSession (real service, Slice D)', () => {
  it('starts in the loading (pending) state', () => {
    getIdeationEmbedSession.mockReturnValue(new Promise(() => {})); // never resolves
    const { result } = renderHook(() => useIdeationEmbedSession(), {
      wrapper: Wrapper,
    });
    expect(result.current.isPending).toBe(true);
    expect(result.current.data).toBeUndefined();
  });

  it('resolves to the minted board embed session from the service', async () => {
    getIdeationEmbedSession.mockResolvedValue({
      iframe_url: 'https://shared.test/embed/ideas',
      token: 'embed-token-xyz',
      expires_at: '2026-07-19T00:15:00+00:00',
    });
    const { result } = renderHook(() => useIdeationEmbedSession(), {
      wrapper: Wrapper,
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(getIdeationEmbedSession).toHaveBeenCalledWith(undefined);
    expect(result.current.data?.token).toBe('embed-token-xyz');
    expect(result.current.data?.iframe_url).toContain('/embed/ideas');
  });

  it('passes the idea id through for the detail view', async () => {
    getIdeationEmbedSession.mockResolvedValue({
      iframe_url: 'https://shared.test/embed/ideas/idea-123',
      token: 't',
      expires_at: 'x',
    });
    const { result } = renderHook(() => useIdeationEmbedSession('idea-123'), {
      wrapper: Wrapper,
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(getIdeationEmbedSession).toHaveBeenCalledWith('idea-123');
    expect(result.current.data?.iframe_url).toContain('/embed/ideas/idea-123');
  });

  it('surfaces the error state (retry CTA) when the mint fails', async () => {
    getIdeationEmbedSession.mockRejectedValue(new Error('Failed to open the Ideas workspace'));
    const { result } = renderHook(() => useIdeationEmbedSession(), {
      wrapper: Wrapper,
    });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.data).toBeUndefined();

    // A manual retry (the AC-44 CTA) refetches; on recovery it resolves.
    getIdeationEmbedSession.mockResolvedValue({
      iframe_url: 'https://shared.test/embed/ideas',
      token: 't2',
      expires_at: 'x',
    });
    await result.current.refetch();
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.token).toBe('t2');
  });
});
