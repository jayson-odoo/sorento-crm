/**
 * useMarket hooks - useRunResearch running→complete→failed + toast copy, and the
 * topic mutation hooks (create/update/delete) invalidating the topics query.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const svc = vi.hoisted(() => ({
  runMarketResearch: vi.fn(),
  createMarketTopic: vi.fn(),
  updateMarketTopic: vi.fn(),
  deleteMarketTopic: vi.fn(),
  listMarketSignals: vi.fn(),
  listMarketTopics: vi.fn(),
  getMarketResearchRun: vi.fn(),
}));
vi.mock('../services/marketService', () => svc);

const toastSuccess = vi.fn();
const toastError = vi.fn();
vi.mock('@/lib/toast', () => ({
  toast: {
    success: (...a: unknown[]) => toastSuccess(...a),
    error: (...a: unknown[]) => toastError(...a),
  },
}));

import {
  useRunResearch,
  useCreateTopic,
  useUpdateTopic,
  useDeleteTopic,
} from './useMarket';
import type { MarketResearchRun } from '../types/market.types';

function completedRun(over: Partial<MarketResearchRun> = {}): MarketResearchRun {
  return {
    id: 'run-1',
    status: 'completed',
    started_at: '2026-07-10T08:00:00',
    finished_at: '2026-07-10T08:01:00',
    topic_count: 3,
    signal_count: 2,
    error: null,
    ...over,
  };
}

function makeWrapper() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidate = vi.spyOn(client, 'invalidateQueries');
  const wrapper = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client }, children);
  return { wrapper, invalidate };
}

beforeEach(() => {
  Object.values(svc).forEach((f) => f.mockReset());
  toastSuccess.mockReset();
  toastError.mockReset();
});

describe('useRunResearch', () => {
  it('runs to completion, invalidates signals, and toasts the fresh-signal count', async () => {
    svc.runMarketResearch.mockResolvedValue(completedRun({ signal_count: 2 }));
    const { wrapper, invalidate } = makeWrapper();
    const { result } = renderHook(() => useRunResearch(), { wrapper });

    await act(async () => {
      await result.current.start();
    });

    await waitFor(() => expect(result.current.isComplete).toBe(true));
    expect(result.current.run?.signal_count).toBe(2);
    expect(result.current.isRunning).toBe(false);
    expect(result.current.isFailed).toBe(false);
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['scm', 'market', 'signals'] });
    expect(toastSuccess).toHaveBeenCalledWith(
      'Research complete - 2 new market signals captured',
    );
  });

  it('toasts the no-new-signals copy when nothing was captured', async () => {
    svc.runMarketResearch.mockResolvedValue(completedRun({ signal_count: 0 }));
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useRunResearch(), { wrapper });
    await act(async () => {
      await result.current.start();
    });
    await waitFor(() => expect(result.current.isComplete).toBe(true));
    expect(toastSuccess).toHaveBeenCalledWith('Research complete - no new signals this run');
  });

  it('surfaces a failed run + error toast when the run rejects', async () => {
    svc.runMarketResearch.mockRejectedValue(new Error('Anthropic web-search not configured'));
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useRunResearch(), { wrapper });

    await act(async () => {
      await result.current.start();
    });

    await waitFor(() => expect(result.current.isFailed).toBe(true));
    expect(result.current.error).toBe('Anthropic web-search not configured');
    expect(result.current.run?.status).toBe('failed');
    expect(toastError).toHaveBeenCalledWith('Anthropic web-search not configured');
  });

  it('reset clears the run + error back to idle', async () => {
    svc.runMarketResearch.mockResolvedValue(completedRun());
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useRunResearch(), { wrapper });
    await act(async () => {
      await result.current.start();
    });
    await waitFor(() => expect(result.current.isComplete).toBe(true));
    act(() => result.current.reset());
    expect(result.current.run).toBeNull();
    expect(result.current.error).toBeNull();
  });
});

describe('topic mutation hooks invalidate the topics query', () => {
  it('useCreateTopic invalidates topics + toasts on success', async () => {
    svc.createMarketTopic.mockResolvedValue({});
    const { wrapper, invalidate } = makeWrapper();
    const { result } = renderHook(() => useCreateTopic(), { wrapper });
    await act(async () => {
      await result.current.mutateAsync({
        label: 'X', category_ref: null, currency: null,
        search_prompt: 'y', cadence: 'weekly', is_active: true,
      });
    });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['scm', 'market', 'topics'] });
    expect(toastSuccess).toHaveBeenCalledWith('Research topic created');
  });

  it('useUpdateTopic invalidates topics + toasts on success', async () => {
    svc.updateMarketTopic.mockResolvedValue({});
    const { wrapper, invalidate } = makeWrapper();
    const { result } = renderHook(() => useUpdateTopic(), { wrapper });
    await act(async () => {
      await result.current.mutateAsync({
        id: 't-1',
        body: { label: 'X', category_ref: null, currency: null, search_prompt: 'y', cadence: 'weekly', is_active: true },
      });
    });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['scm', 'market', 'topics'] });
    expect(toastSuccess).toHaveBeenCalledWith('Research topic updated');
  });

  it('useDeleteTopic invalidates topics on success', async () => {
    svc.deleteMarketTopic.mockResolvedValue(undefined);
    const { wrapper, invalidate } = makeWrapper();
    const { result } = renderHook(() => useDeleteTopic(), { wrapper });
    await act(async () => {
      await result.current.mutateAsync('t-1');
    });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['scm', 'market', 'topics'] });
  });

  it('useCreateTopic toasts the error message on failure', async () => {
    svc.createMarketTopic.mockRejectedValue(new Error('boom'));
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useCreateTopic(), { wrapper });
    await act(async () => {
      await result.current
        .mutateAsync({ label: 'X', category_ref: null, currency: null, search_prompt: 'y', cadence: 'weekly', is_active: true })
        .catch(() => {});
    });
    expect(toastError).toHaveBeenCalledWith('boom');
  });
});
