/**
 * useAutocountPull - SR2 red test.
 *
 * AC-BD-6: the pull page polls the pull status every 10 seconds while `building` or
 * `previewing`, and stops on `review`, `failed`, `expired` and `confirmed`.
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

function pullWithPhase(phase: string) {
  return {
    job_id: 'job-1',
    entity: 'products',
    phase,
    progress: null,
    header: null,
    counts: null,
    confirm_blocked_reason: null,
    compare: null,
    apply_job_id: null,
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

  it.each(['review', 'failed', 'expired', 'confirmed'])(
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
