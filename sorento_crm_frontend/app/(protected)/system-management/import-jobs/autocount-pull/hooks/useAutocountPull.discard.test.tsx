/**
 * useDiscardPull - RED test (AC-DS-10 toast half).
 *
 * Plan: documentation/plans/autocount/PLAN-autocount-pull-discard.md
 * UAC:  documentation/plans/autocount/autocount-pull-discard-acceptance-criteria.md
 *
 * `AutocountPullReview.discard.test.tsx` mocks `hooks/useAutocountPull` wholesale (component
 * in isolation, per repo convention) so it cannot see what the REAL hook's `onSuccess`/`onError`
 * actually does - that half (toasts "Pull discarded" on success, the extracted API error message
 * on failure, mirroring `useConfirmPull`) is exercised here instead, against the real hook with
 * only the SERVICE and `@/lib/toast` mocked (hook -> service, per layering).
 *
 * A separate file, not an addition to the existing `useAutocountPull.test.tsx`: that file
 * statically imports `usePull` by name from the real module at the top, so adding
 * `useDiscardPull` to the same import line would fail the WHOLE file at collection (all H1a..H1e
 * tests, currently green) the instant the named export does not exist yet - not just the new
 * test. A brand-new file has no such existing coverage to put at risk.
 *
 * RED reason today: `useDiscardPull` is not exported by `./useAutocountPull` at all.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const toastSuccess = vi.fn();
const toastError = vi.fn();
vi.mock('@/lib/toast', () => ({
  toast: {
    success: (...a: unknown[]) => toastSuccess(...a),
    error: (...a: unknown[]) => toastError(...a),
  },
}));

const discardPull = vi.fn();
vi.mock('../services/autocountPullService', () => ({
  discardPull: (...a: unknown[]) => discardPull(...a),
  getPull: vi.fn(),
  getCurrentPull: vi.fn(),
  startPull: vi.fn(),
  getPullRows: vi.fn(),
  downloadPullXlsx: vi.fn(),
  comparePull: vi.fn(),
  confirmPull: vi.fn(),
}));

// Namespace import (see module docstring): a missing `useDiscardPull` export reds only the
// tests below, never a whole-file collection failure.
import * as autocountPullHooks from './useAutocountPull';

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return React.createElement(QueryClientProvider, { client }, children);
}

beforeEach(() => {
  discardPull.mockReset();
  toastSuccess.mockClear();
  toastError.mockClear();
});

describe('useDiscardPull (AC-DS-10)', () => {
  it('DH1: success toasts "Pull discarded"', async () => {
    discardPull.mockResolvedValue({ job_id: 'job-1', entity: 'products', phase: 'discarded' });

    const { result } = renderHook(() => autocountPullHooks.useDiscardPull(), { wrapper });

    await act(async () => {
      result.current.mutate('job-1');
    });

    await waitFor(() => expect(toastSuccess).toHaveBeenCalledWith('Pull discarded'));
    expect(discardPull).toHaveBeenCalledWith('job-1');
  });

  it('DH2: a failure toasts the extracted API error message, never a raw error object', async () => {
    discardPull.mockRejectedValue(new Error("Pull is in phase 'confirmed'; it cannot be discarded."));

    const { result } = renderHook(() => autocountPullHooks.useDiscardPull(), { wrapper });

    await act(async () => {
      result.current.mutate('job-1');
    });

    await waitFor(() =>
      expect(toastError).toHaveBeenCalledWith("Pull is in phase 'confirmed'; it cannot be discarded."),
    );
  });

  it('DH3: also invalidates the generic job query (S3, Phase 3 fix round 1) - the Job Summary card and its Cancel Job button, which read `[\'import-job\', id]`, must refresh after a discard from `building` too', async () => {
    discardPull.mockResolvedValue({ job_id: 'job-1', entity: 'products', phase: 'discarded' });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidateSpy = vi.spyOn(client, 'invalidateQueries');
    function localWrapper({ children }: { children: React.ReactNode }) {
      return React.createElement(QueryClientProvider, { client }, children);
    }

    const { result } = renderHook(() => autocountPullHooks.useDiscardPull(), { wrapper: localWrapper });

    await act(async () => {
      result.current.mutate('job-1');
    });

    // Prefix form (no `id`) - `[id]/page.tsx`'s own job query key is `['import-job', id]`,
    // and this hook only ever sees `pull.job_id`, not the URL's own (possibly different,
    // per E2) `id` param - a prefix invalidates every query keyed under `import-job`
    // regardless of which id it was mounted with.
    await waitFor(() => expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['import-job'] }));
  });
});
