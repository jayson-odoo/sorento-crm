import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));

const toastError = vi.fn();
vi.mock('sonner', () => ({ toast: { error: (...a: unknown[]) => toastError(...a) } }));

import { useReorderRun } from './useReorderRun';

function jsonRes(body: unknown, ok = true, status = 200) {
  return {
    ok,
    status,
    headers: { get: () => 'application/json' },
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as unknown as Response;
}

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return React.createElement(QueryClientProvider, { client }, children);
}

/** Route the mocked apiFetch by method: POST = create, GET = poll (queued outcomes). */
function routeApi(pollOutcomes: unknown[]) {
  let i = 0;
  apiFetch.mockImplementation((url: string, init?: RequestInit) => {
    if (init?.method === 'POST') {
      return Promise.resolve(
        jsonRes({ run_id: 'run-42', status: 'running', buy_scope: 'network', stage: 'resolving_policies' }, true, 202),
      );
    }
    const next = pollOutcomes[Math.min(i, pollOutcomes.length - 1)];
    i += 1;
    return Promise.resolve(jsonRes(next));
  });
}

const COMPLETED = {
  run_id: 'run-42',
  status: 'completed',
  stage: 'writing_recommendations',
  buy_scope: 'network',
  error: null,
  summary: {
    buy_count: 3,
    disposition_count: 1,
    exception_count: 1,
    total_cash_impact: 5000,
    recommendation_count: 4,
  },
};

const RUNNING = {
  run_id: 'run-42',
  status: 'running',
  stage: 'resolving_policies',
  buy_scope: 'network',
  error: null,
  summary: null,
};

beforeEach(() => {
  apiFetch.mockReset();
  toastError.mockReset();
});

describe('useReorderRun — lifecycle', () => {
  it('POSTs then polls to completion, exposing the summary', async () => {
    routeApi([RUNNING, COMPLETED]);
    const { result } = renderHook(() => useReorderRun(), { wrapper });

    await act(async () => {
      await result.current.start({ warehouse_codes: ['WH-KL'], buy_scope: 'network' });
    });

    // POST fired with the run request
    expect(apiFetch).toHaveBeenCalledWith(
      '/api/v1/scm/reorder-runs',
      expect.objectContaining({ method: 'POST' }),
    );

    // polls until the background job completes
    await waitFor(() => expect(result.current.isComplete).toBe(true), { timeout: 3000 });
    expect(result.current.run?.summary?.recommendation_count).toBe(4);
    expect(result.current.isRunning).toBe(false);
    // the poll GET was hit
    expect(apiFetch).toHaveBeenCalledWith('/api/v1/scm/reorder-runs/run-42');
  });

  it('reflects a running run before it terminates', async () => {
    routeApi([RUNNING]);
    const { result } = renderHook(() => useReorderRun(), { wrapper });
    await act(async () => {
      await result.current.start({ warehouse_codes: ['WH-KL'], buy_scope: 'network' });
    });
    await waitFor(() => expect(result.current.isRunning).toBe(true));
    expect(result.current.stageIndex).toBe(0);
    expect(result.current.isComplete).toBe(false);
  });

  it('surfaces a failed run with its error message', async () => {
    routeApi([{ ...RUNNING, status: 'failed', error: 'Engine crashed writing recommendations' }]);
    const { result } = renderHook(() => useReorderRun(), { wrapper });
    await act(async () => {
      await result.current.start({ warehouse_codes: ['WH-KL'], buy_scope: 'network' });
    });
    await waitFor(() => expect(result.current.isFailed).toBe(true));
    expect(result.current.error).toBe('Engine crashed writing recommendations');
  });

  it('surfaces a POST failure as a failed state + toast', async () => {
    apiFetch.mockResolvedValue(jsonRes({ detail: 'Not allowed to run planning' }, false, 403));
    const { result } = renderHook(() => useReorderRun(), { wrapper });
    await act(async () => {
      await result.current.start({ warehouse_codes: ['WH-KL'], buy_scope: 'network' });
    });
    expect(result.current.isFailed).toBe(true);
    expect(result.current.error).toBe('Not allowed to run planning');
    expect(toastError).toHaveBeenCalled();
  });

  it('stops polling and surfaces a stalled state once the poll cap elapses', async () => {
    vi.useFakeTimers();
    try {
      routeApi([RUNNING]); // never terminates — simulates an orphaned run
      const { result } = renderHook(() => useReorderRun(), { wrapper });
      await act(async () => {
        await result.current.start({ warehouse_codes: ['WH-KL'], buy_scope: 'network' });
      });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(2_000);
      });
      expect(result.current.isRunning).toBe(true);
      expect(result.current.isStalled).toBe(false);

      // advance past the 3-minute poll cap
      await act(async () => {
        await vi.advanceTimersByTimeAsync(3 * 60 * 1_000);
      });
      expect(result.current.isStalled).toBe(true);
      expect(result.current.isRunning).toBe(false);

      // polling has stopped — no further GETs beyond what already fired
      const getsBefore = apiFetch.mock.calls.filter(
        (c) => (c[1] as RequestInit | undefined)?.method !== 'POST',
      ).length;
      await act(async () => {
        await vi.advanceTimersByTimeAsync(10_000);
      });
      const getsAfter = apiFetch.mock.calls.filter(
        (c) => (c[1] as RequestInit | undefined)?.method !== 'POST',
      ).length;
      expect(getsAfter).toBe(getsBefore);
    } finally {
      vi.useRealTimers();
    }
  });

  it('reset clears the run back to idle', async () => {
    routeApi([COMPLETED]);
    const { result } = renderHook(() => useReorderRun(), { wrapper });
    await act(async () => {
      await result.current.start({ warehouse_codes: ['WH-KL'], buy_scope: 'network' });
    });
    await waitFor(() => expect(result.current.isComplete).toBe(true));
    act(() => result.current.reset());
    expect(result.current.run).toBeNull();
  });
});
