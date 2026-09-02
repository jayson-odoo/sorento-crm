/**
 * SCM Coverage Timeline hooks (UAC Group B).
 *
 * Two properties matter and both are cheap to break:
 *
 * - LAZY. Nothing is fetched until the row's dialog is open AND there is a pool to
 *    date against, so opening the plan grid never costs N timelines.
 * - KEYED ON THE ROW. The query key carries product + pool + floor, so stepping the
 *    dialog to the next record refetches instead of leaving the previous row's
 *    timeline on screen under a new heading, which would be a wrong answer presented
 *    confidently.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const getCoverageTimeline = vi.fn();
const acceptCoverageTransfer = vi.fn();
vi.mock('../services/coverageService', () => ({
  getCoverageTimeline: (...a: unknown[]) => getCoverageTimeline(...a),
  acceptCoverageTransfer: (...a: unknown[]) => acceptCoverageTransfer(...a),
}));

const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock('@/lib/toast', () => ({ toast }));

import { coverageKey, useAcceptCoverageTransfer, useCoverageTimeline } from './useCoverage';

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return React.createElement(QueryClientProvider, { client }, children);
}

const QUERY = { product_code: 'SRTBS4832', pool_code: 'BRW', floor: 0, product_name: 'Basin' };

beforeEach(() => {
  getCoverageTimeline.mockReset().mockResolvedValue({ product_code: 'SRTBS4832' });
  acceptCoverageTransfer
    .mockReset()
    .mockResolvedValue({ proposal_ref: 'TP-1', accepted: true, transfer_ref: 'TRF-9' });
  toast.success.mockReset();
  toast.error.mockReset();
});

describe('useCoverageTimeline', () => {
  it('does NOT fetch while the dialog is closed', () => {
    renderHook(() => useCoverageTimeline(QUERY, false), { wrapper });
    expect(getCoverageTimeline).not.toHaveBeenCalled();
  });

  it('does NOT fetch a network row, which has no single pool to date against', () => {
    renderHook(() => useCoverageTimeline({ ...QUERY, pool_code: '' }, true), { wrapper });
    expect(getCoverageTimeline).not.toHaveBeenCalled();
  });

  it('fetches with the human codes and the floor once the dialog opens', async () => {
    const { result } = renderHook(() => useCoverageTimeline({ ...QUERY, floor: 8 }, true), {
      wrapper,
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(getCoverageTimeline).toHaveBeenCalledWith({
      product_code: 'SRTBS4832',
      pool_code: 'BRW',
      floor: 8,
      product_name: 'Basin',
    });
  });

  it('refetches when the dialog steps to another record', async () => {
    const { result, rerender } = renderHook(
      ({ code }: { code: string }) =>
        useCoverageTimeline({ ...QUERY, product_code: code }, true),
      { wrapper, initialProps: { code: 'SRTBS4832' } },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    rerender({ code: 'SRTWT7408' });
    await waitFor(() => expect(getCoverageTimeline).toHaveBeenCalledTimes(2));
    expect(getCoverageTimeline).toHaveBeenLastCalledWith(
      expect.objectContaining({ product_code: 'SRTWT7408' }),
    );
  });

  it('keys on product, pool and floor so no two rows share a cache entry', () => {
    expect(coverageKey(QUERY)).toEqual(['scm', 'reorder', 'coverage', 'SRTBS4832', 'BRW', 0]);
    expect(coverageKey({ ...QUERY, pool_code: 'MWH' })).not.toEqual(coverageKey(QUERY));
    expect(coverageKey({ ...QUERY, floor: 8 })).not.toEqual(coverageKey(QUERY));
  });
});

describe('useAcceptCoverageTransfer', () => {
  it('accepts by proposal_ref and toasts the created transfer reference', async () => {
    const { result } = renderHook(() => useAcceptCoverageTransfer(QUERY), { wrapper });
    result.current.mutate('TP-MWH-0001');
    await waitFor(() => expect(acceptCoverageTransfer).toHaveBeenCalledWith('TP-MWH-0001'));
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('Transfer accepted - TRF-9'));
  });

  it('toasts the backend message when the acceptance fails', async () => {
    acceptCoverageTransfer.mockRejectedValue(new Error('Proposal already accepted'));
    const { result } = renderHook(() => useAcceptCoverageTransfer(QUERY), { wrapper });
    result.current.mutate('TP-MWH-0001');
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Proposal already accepted'));
  });
});
