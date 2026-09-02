/**
 * useProductSetProposals - the query/mutation layer between the review screen
 * and productSetProposalService. Covers what the component test does not: the
 * cache write on a successful scan, the toast wording for an empty vs. a
 * non-empty pass, cache invalidation on apply, and that a per-set refusal is
 * named rather than swallowed.
 *
 * UAC group H: `documentation/plans/master-data/product-sets-acceptance-criteria.md`.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));
vi.mock('../services/productSetProposalService', () => ({
  getProductSetProposals: vi.fn(),
  runProductSetProposals: vi.fn(),
  applyProductSetProposals: vi.fn(),
}));

import { toast } from '@/lib/toast';
import {
  getProductSetProposals,
  runProductSetProposals,
  applyProductSetProposals,
} from '../services/productSetProposalService';
import {
  useApplyProductSetProposals,
  useProductSetProposals,
  useRunProductSetProposals,
} from './useProductSetProposals';
import type { ProductSetProposalBatch } from '../types/productSetProposal.types';

const mockGet = vi.mocked(getProductSetProposals);
const mockRun = vi.mocked(runProductSetProposals);
const mockApply = vi.mocked(applyProductSetProposals);

const KEY = ['product-set-proposals'];

function wrapper(client: QueryClient) {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

function batchFixture(overrides: Partial<ProductSetProposalBatch> = {}): ProductSetProposalBatch {
  return {
    id: 'batch-1',
    company_name: 'Sorento',
    created_at: '2026-08-24T00:00:00Z',
    created_by_name: 'Jane Tan',
    family_count: 1,
    proposal_count: 1,
    proposals: [],
    ...overrides,
  };
}

beforeEach(() => vi.clearAllMocks());

describe('useProductSetProposals', () => {
  it('fetches through the service and exposes the batch', async () => {
    mockGet.mockResolvedValue(batchFixture());
    const client = new QueryClient();

    const { result } = renderHook(() => useProductSetProposals(), { wrapper: wrapper(client) });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledTimes(1);
    expect(result.current.data?.id).toBe('batch-1');
  });
});

describe('useRunProductSetProposals', () => {
  it('writes the fresh batch into the query cache on success', async () => {
    const fresh = batchFixture({ id: 'batch-2', proposal_count: 3, family_count: 2 });
    mockRun.mockResolvedValue(fresh);
    const client = new QueryClient();

    const { result } = renderHook(() => useRunProductSetProposals(), {
      wrapper: wrapper(client),
    });
    result.current.mutate();

    await waitFor(() => expect(client.getQueryData(KEY)).toEqual(fresh));
  });

  it('toasts the "nothing to propose" message when the pass finds zero families', async () => {
    mockRun.mockResolvedValue(batchFixture({ proposal_count: 0, family_count: 0 }));
    const client = new QueryClient();

    const { result } = renderHook(() => useRunProductSetProposals(), {
      wrapper: wrapper(client),
    });
    result.current.mutate();

    await waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith(
        'No new sets to propose - every family the catalogue names already has one',
      ),
    );
  });

  it('toasts the proposal/family counts when the pass finds candidates', async () => {
    mockRun.mockResolvedValue(batchFixture({ proposal_count: 3, family_count: 2 }));
    const client = new QueryClient();

    const { result } = renderHook(() => useRunProductSetProposals(), {
      wrapper: wrapper(client),
    });
    result.current.mutate();

    await waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith('3 sets proposed across 2 families'),
    );
  });

  it('toasts the extracted error message on failure', async () => {
    mockRun.mockRejectedValue(new Error('Not permitted to scan the catalogue'));
    const client = new QueryClient();

    const { result } = renderHook(() => useRunProductSetProposals(), {
      wrapper: wrapper(client),
    });
    result.current.mutate();

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('Not permitted to scan the catalogue'),
    );
  });
});

describe('useApplyProductSetProposals', () => {
  it('invalidates both the proposals batch and the product-sets list on success', async () => {
    mockApply.mockResolvedValue({ applied: [{ proposal_id: 'p1', set_code: 'SRTWC8608' }], refused: [] });
    const client = new QueryClient();
    const invalidateSpy = vi.spyOn(client, 'invalidateQueries');

    const { result } = renderHook(() => useApplyProductSetProposals(), {
      wrapper: wrapper(client),
    });
    result.current.mutate(['p1']);

    await waitFor(() => expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: KEY }));
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['product-sets'] });
  });

  it('toasts the created count, and names every refusal by set code and reason', async () => {
    mockApply.mockResolvedValue({
      applied: [{ proposal_id: 'p1', set_code: 'SRTWC8608' }],
      refused: [{ proposal_id: 'p2', set_code: 'SRTWC8609', reason: 'code already exists' }],
    });
    const client = new QueryClient();

    const { result } = renderHook(() => useApplyProductSetProposals(), {
      wrapper: wrapper(client),
    });
    result.current.mutate(['p1', 'p2']);

    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('1 set created'));
    expect(toast.error).toHaveBeenCalledWith(
      'SRTWC8609 was not created: code already exists',
    );
  });

  it('does not claim success when every ticked candidate was refused', async () => {
    mockApply.mockResolvedValue({
      applied: [],
      refused: [{ proposal_id: 'p1', set_code: 'SRTWC8608', reason: 'discontinued member' }],
    });
    const client = new QueryClient();

    const { result } = renderHook(() => useApplyProductSetProposals(), {
      wrapper: wrapper(client),
    });
    result.current.mutate(['p1']);

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        'SRTWC8608 was not created: discontinued member',
      ),
    );
    expect(toast.success).not.toHaveBeenCalled();
  });

  it('toasts the extracted error message when the request itself fails', async () => {
    mockApply.mockRejectedValue(new Error('proposal_ids must not be empty'));
    const client = new QueryClient();

    const { result } = renderHook(() => useApplyProductSetProposals(), {
      wrapper: wrapper(client),
    });
    result.current.mutate([]);

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('proposal_ids must not be empty'),
    );
  });
});
