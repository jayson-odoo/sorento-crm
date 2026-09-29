/**
 * useAutocountPull - SR2 red test.
 *
 * AC-BD-6: the pull page polls the pull status every 10 seconds while `building` or
 * `previewing`, and stops on `review`, `failed`, `expired`. `confirmed` (fix round 3, item 2)
 * is NOT an unconditional stop: the apply task's own `stock_list_not_archived` warning lands
 * on the pull's metadata only once the apply task actually runs, after `phase` has already
 * flipped to `confirmed`, so the poll continues while `apply_status` is not yet terminal
 * (`finished`/`failed`) and stops once it is.
 *
 * `usePull`'s `refetchInterval` callback already reads `query.state.data?.phase` correctly in
 * Phase 1 code, so this exercises it against the REAL `getPull` service call (mocked at the
 * service module, per FE layering: hook -> service). RED reason today: `getPull` still resolves
 * through `autocountPullService`'s `USE_MOCK` branch when this file is actually wired in SR2 -
 * mocking the service module here isolates the hook's own polling logic from that, so this test
 * should already demonstrate the interval logic; it is listed to guard against a refactor that
 * breaks it once the service is rewired, and is expected to already pass (GREEN) as a guard.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const getPull = vi.fn();
vi.mock('../services/autocountPullService', () => ({
  getPull: (...a: unknown[]) => getPull(...a),
  getCurrentPull: vi.fn(),
  startPull: vi.fn(),
  getPullRows: vi.fn(),
  downloadPullXlsx: vi.fn(),
  comparePull: vi.fn(),
  confirmPull: vi.fn(),
}));

import { usePull } from './useAutocountPull';

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return React.createElement(QueryClientProvider, { client }, children);
}

function pullWithPhase(phase: string, applyStatus: string | null = null) {
  return {
    job_id: 'job-1',
    entity: 'products',
    phase,
    progress: null,
    header: null,
    counts: null,
    confirm_blocked_reason: null,
    compare: null,
    apply_job_id: phase === 'confirmed' ? 'apply-1' : null,
    apply_status: applyStatus,
    warnings: [],
  };
}

beforeEach(() => {
  getPull.mockReset();
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe('usePull polling (AC-BD-6)', () => {
  it('H1a: refetches roughly every 10s while phase is building', async () => {
    getPull.mockResolvedValue(pullWithPhase('building'));
    renderHook(() => usePull('job-1'), { wrapper });

    await vi.waitFor(() => expect(getPull).toHaveBeenCalledTimes(1));

    await vi.advanceTimersByTimeAsync(10000);
    await vi.waitFor(() => expect(getPull.mock.calls.length).toBeGreaterThanOrEqual(2));

    await vi.advanceTimersByTimeAsync(10000);
    await vi.waitFor(() => expect(getPull.mock.calls.length).toBeGreaterThanOrEqual(3));
  });

  it('H1b: refetches while phase is previewing', async () => {
    getPull.mockResolvedValue(pullWithPhase('previewing'));
    renderHook(() => usePull('job-1'), { wrapper });

    await vi.waitFor(() => expect(getPull).toHaveBeenCalledTimes(1));
    await vi.advanceTimersByTimeAsync(10000);
    await vi.waitFor(() => expect(getPull.mock.calls.length).toBeGreaterThanOrEqual(2));
  });

  it.each(['review', 'failed', 'expired'])(
    'H1c: stops polling once phase is %s',
    async (phase) => {
      getPull.mockResolvedValue(pullWithPhase(phase));
      renderHook(() => usePull('job-1'), { wrapper });

      await vi.waitFor(() => expect(getPull).toHaveBeenCalledTimes(1));
      const callsAfterFirst = getPull.mock.calls.length;

      await vi.advanceTimersByTimeAsync(30000);
      // No further calls - the interval callback returned `false`.
      expect(getPull.mock.calls.length).toBe(callsAfterFirst);
    },
  );
});

describe('usePull keeps polling while the tab is hidden (D27, AC-BV-1)', () => {
  it('F1: passes refetchIntervalInBackground true, so a hidden tab is at most 10s stale', async () => {
    getPull.mockResolvedValue(pullWithPhase('building'));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    function localWrapper({ children }: { children: React.ReactNode }) {
      return React.createElement(QueryClientProvider, { client }, children);
    }
    renderHook(() => usePull('job-1'), { wrapper: localWrapper });

    await vi.waitFor(() => expect(getPull).toHaveBeenCalledTimes(1));

    const observer = client.getQueryCache().find({ queryKey: ['autocount-pull', 'job-1'] })
      ?.observers[0];
    expect(observer?.options.refetchIntervalInBackground).toBe(true);
  });
});

describe('usePull polling while confirmed (fix round 3, item 2)', () => {
  it.each(['queued', 'started'])(
    'H1d: keeps refetching every 10s while phase is confirmed and apply_status is %s',
    async (applyStatus) => {
      getPull.mockResolvedValue(pullWithPhase('confirmed', applyStatus));
      renderHook(() => usePull('job-1'), { wrapper });

      await vi.waitFor(() => expect(getPull).toHaveBeenCalledTimes(1));
      await vi.advanceTimersByTimeAsync(10000);
      await vi.waitFor(() => expect(getPull.mock.calls.length).toBeGreaterThanOrEqual(2));
    },
  );

  it.each(['finished', 'failed'])(
    'H1e: stops polling once phase is confirmed and apply_status is %s',
    async (applyStatus) => {
      getPull.mockResolvedValue(pullWithPhase('confirmed', applyStatus));
      renderHook(() => usePull('job-1'), { wrapper });

      await vi.waitFor(() => expect(getPull).toHaveBeenCalledTimes(1));
      const callsAfterFirst = getPull.mock.calls.length;

      await vi.advanceTimersByTimeAsync(30000);
      // No further calls - the apply job has reached a terminal state.
      expect(getPull.mock.calls.length).toBe(callsAfterFirst);
    },
  );
});
