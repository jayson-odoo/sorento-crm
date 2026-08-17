/**
 * The flyer spec proposal hooks (AC-D.8).
 *
 * Two behaviours matter here and are invisible from the screen:
 *
 * - the 3 s poll runs only while a batch is `proposing`, both for the one
 *   reading's detail query and for the Master Data list; it stops the moment
 *   nothing is (mirrors `useFlyerReadings.test.tsx`'s poll assertions).
 * - `apply` invalidates BOTH query keys - the section the propose button sits
 *   in reads the proposals key, the Master Data list reads the batches key,
 *   and a merchandiser who applies from one screen must see the other agree
 *   without a manual refresh.
 */
import React from 'react';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

vi.mock('../services/flyerSpecProposalService', () => ({
  listFlyerSpecBatches: vi.fn(),
  getFlyerSpecProposals: vi.fn(),
  proposeFlyerSpecs: vi.fn(),
  applyFlyerSpecProposals: vi.fn(),
}));

import { toast } from 'sonner';
import {
  applyFlyerSpecProposals,
  getFlyerSpecProposals,
  listFlyerSpecBatches,
  proposeFlyerSpecs,
  type FlyerSpecBatch,
  type FlyerSpecProposals,
} from '../services/flyerSpecProposalService';
import {
  FLYER_SPEC_BATCHES_QUERY_KEY,
  FLYER_SPEC_PROPOSALS_QUERY_KEY,
  useApplyFlyerSpecProposals,
  useFlyerSpecBatchesQuery,
  useFlyerSpecProposalsQuery,
  useProposeFlyerSpecs,
} from './useFlyerSpecProposals';

const mockList = vi.mocked(listFlyerSpecBatches);
const mockGet = vi.mocked(getFlyerSpecProposals);
const mockPropose = vi.mocked(proposeFlyerSpecs);
const mockApply = vi.mocked(applyFlyerSpecProposals);

function wrapperWith(client: QueryClient) {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

function freshClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

function batch(overrides: Partial<FlyerSpecBatch> = {}): FlyerSpecBatch {
  return {
    id: 'batch-1',
    reading_id: 'r-1',
    filename: 'flyer.pdf',
    status: 'proposed',
    error_message: null,
    product_count: 1,
    proposal_count: 1,
    new_count: 1,
    change_count: 0,
    conflict_count: 0,
    unchanged_count: 0,
    suppressed_count: 0,
    applied_count: 0,
    read_at: null,
    created_at: null,
    finished_at: null,
    applied_at: null,
    created_by_name: null,
    applied_by_name: null,
    ...overrides,
  };
}

function proposals(overrides: Partial<FlyerSpecProposals> = {}): FlyerSpecProposals {
  return { ...batch(), groups: [], ...overrides };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('useFlyerSpecBatchesQuery, the 3 s poll (AC-D.8)', () => {
  it('lists the batches', async () => {
    mockList.mockResolvedValue([batch()]);

    const { result } = renderHook(() => useFlyerSpecBatchesQuery(), {
      wrapper: wrapperWith(freshClient()),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveLength(1);
  });

  it('polls every 3s while a batch is proposing, and stops once none is', async () => {
    // Real timers: react-query's own refetch scheduling runs through a real
    // setTimeout, and `waitFor` polls with real timers too.
    mockList.mockResolvedValueOnce([batch({ status: 'proposing' })]);
    mockList.mockResolvedValue([batch({ status: 'proposed' })]);

    const { result } = renderHook(() => useFlyerSpecBatchesQuery(), {
      wrapper: wrapperWith(freshClient()),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockList).toHaveBeenCalledTimes(1);

    await waitFor(() => expect(result.current.data?.[0]?.status).toBe('proposed'), {
      timeout: 4500,
    });
    expect(mockList).toHaveBeenCalledTimes(2);

    // Nothing left proposing: refetchInterval resolves to false, so no third
    // GET turns up even after another full poll interval elapses.
    await new Promise((resolve) => setTimeout(resolve, 3200));
    expect(mockList).toHaveBeenCalledTimes(2);
  }, 10000);

  it('never polls when nothing is proposing to begin with', async () => {
    mockList.mockResolvedValue([batch({ status: 'proposed' })]);

    const { result } = renderHook(() => useFlyerSpecBatchesQuery(), {
      wrapper: wrapperWith(freshClient()),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockList).toHaveBeenCalledTimes(1);

    await new Promise((resolve) => setTimeout(resolve, 3200));
    expect(mockList).toHaveBeenCalledTimes(1);
  }, 10000);
});

describe('useFlyerSpecProposalsQuery, the 3 s poll (AC-D.8)', () => {
  it('asks for nothing until there is a reading to ask about', () => {
    renderHook(() => useFlyerSpecProposalsQuery(''), { wrapper: wrapperWith(freshClient()) });

    expect(mockGet).not.toHaveBeenCalled();
  });

  it('asks for nothing when the caller withholds it', () => {
    // The route needs `master_data.products.edit`; the reading page renders this
    // section for people who lack it, and a 403 nobody can act on is not worth asking for.
    renderHook(() => useFlyerSpecProposalsQuery('r-1', { enabled: false }), {
      wrapper: wrapperWith(freshClient()),
    });

    expect(mockGet).not.toHaveBeenCalled();
  });

  it('polls every 3s while the batch is proposing, and stops once it settles', async () => {
    mockGet.mockResolvedValueOnce(proposals({ status: 'proposing' }));
    mockGet.mockResolvedValue(proposals({ status: 'proposed' }));

    const { result } = renderHook(() => useFlyerSpecProposalsQuery('r-1'), {
      wrapper: wrapperWith(freshClient()),
    });

    await waitFor(() => expect(result.current.data?.status).toBe('proposing'));
    expect(mockGet).toHaveBeenCalledTimes(1);

    await waitFor(() => expect(result.current.data?.status).toBe('proposed'), { timeout: 4500 });
    expect(mockGet).toHaveBeenCalledTimes(2);

    await new Promise((resolve) => setTimeout(resolve, 3200));
    expect(mockGet).toHaveBeenCalledTimes(2);
  }, 10000);

  it('does not poll a batch that is already settled', async () => {
    mockGet.mockResolvedValue(proposals({ status: 'failed' }));

    const { result } = renderHook(() => useFlyerSpecProposalsQuery('r-1'), {
      wrapper: wrapperWith(freshClient()),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledTimes(1);

    await new Promise((resolve) => setTimeout(resolve, 3200));
    expect(mockGet).toHaveBeenCalledTimes(1);
  }, 10000);
});

describe('useProposeFlyerSpecs', () => {
  it('invalidates both the proposals key and the batches key on success', async () => {
    mockPropose.mockResolvedValue(batch({ status: 'proposing' }));
    const client = freshClient();
    const invalidate = vi.spyOn(client, 'invalidateQueries');

    const { result } = renderHook(() => useProposeFlyerSpecs('r-1'), {
      wrapper: wrapperWith(client),
    });

    result.current.mutate();

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: [FLYER_SPEC_PROPOSALS_QUERY_KEY, 'r-1'],
    });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: [FLYER_SPEC_BATCHES_QUERY_KEY] });
  });

  it('toasts an error, not a success, when the 202 already answers failed', async () => {
    mockPropose.mockResolvedValue(
      batch({ status: 'failed', error_message: 'The flyer could not be queued for reading.' }),
    );

    const { result } = renderHook(() => useProposeFlyerSpecs('r-1'), {
      wrapper: wrapperWith(freshClient()),
    });

    result.current.mutate();

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(vi.mocked(toast.error)).toHaveBeenCalledWith(
      'The flyer could not be queued for reading.',
    );
    expect(vi.mocked(toast.success)).not.toHaveBeenCalled();
  });
});

describe('useApplyFlyerSpecProposals', () => {
  it('invalidates both query keys after a successful apply', async () => {
    mockApply.mockResolvedValue({
      applied: [{ proposal_id: 'p-1', product_code: 'SRTWC8066', spec_key: 'seat_material', value: 'pp' }],
      refused: [],
    });
    const client = freshClient();
    const invalidate = vi.spyOn(client, 'invalidateQueries');

    const { result } = renderHook(() => useApplyFlyerSpecProposals('r-1'), {
      wrapper: wrapperWith(client),
    });

    result.current.mutate(['p-1']);

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: [FLYER_SPEC_PROPOSALS_QUERY_KEY, 'r-1'],
    });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: [FLYER_SPEC_BATCHES_QUERY_KEY] });
    expect(vi.mocked(toast.success)).toHaveBeenCalledWith('1 specification value written');
  });

  it('invalidates both keys even when nothing was written, but does not toast a success', async () => {
    mockApply.mockResolvedValue({
      applied: [],
      refused: [
        {
          proposal_id: 'p-1',
          product_code: 'SRTWC8066',
          spec_key: 'finish',
          reason: 'conflict_not_confirmed',
          message: 'A person set this value.',
        },
      ],
    });
    const client = freshClient();
    const invalidate = vi.spyOn(client, 'invalidateQueries');

    const { result } = renderHook(() => useApplyFlyerSpecProposals('r-1'), {
      wrapper: wrapperWith(client),
    });

    result.current.mutate(['p-1']);

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: [FLYER_SPEC_PROPOSALS_QUERY_KEY, 'r-1'],
    });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: [FLYER_SPEC_BATCHES_QUERY_KEY] });
    expect(vi.mocked(toast.success)).not.toHaveBeenCalled();
  });

  it('passes the reading id and proposal ids straight through to the service', async () => {
    mockApply.mockResolvedValue({ applied: [], refused: [] });

    const { result } = renderHook(() => useApplyFlyerSpecProposals('r-1'), {
      wrapper: wrapperWith(freshClient()),
    });

    result.current.mutate(['p-1', 'p-2']);

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockApply).toHaveBeenCalledWith('r-1', ['p-1', 'p-2']);
  });
});
