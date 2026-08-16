/**
 * useSpecExtraction - the state machine behind the prompt box (Journey B, AC-B.7,
 * AC-B.9's frontend half, AC-B.15's invalidation neighbour).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));
vi.mock('../../product-specifications/services/productSpecService', () => ({
  extractSpecProposals: vi.fn(),
  applySpecProposals: vi.fn(),
}));

import { toast } from 'sonner';
import {
  applySpecProposals,
  extractSpecProposals,
} from '../../product-specifications/services/productSpecService';
import { useSpecExtraction } from './useSpecExtraction';
import { APPLICABLE_KEY, DETAIL_KEY } from './useProductSpecTable';

const mockExtract = extractSpecProposals as unknown as ReturnType<typeof vi.fn>;
const mockApply = applySpecProposals as unknown as ReturnType<typeof vi.fn>;

const PROPOSALS = [
  {
    spec_key: 'seat_material',
    label: 'Seat cover material',
    data_type: 'text',
    value: 'pp',
    unit: null,
    evidence: '*PP Seat Cover',
    kind: 'new' as const,
    stored_value: null,
    stored_unit: null,
    stored_source: null,
  },
  {
    spec_key: 'dim_height',
    label: 'Height',
    data_type: 'numeric',
    value: 770,
    unit: 'mm',
    evidence: 'D: L680xW375xH770mm',
    kind: 'change' as const,
    stored_value: 750,
    stored_unit: 'mm',
    stored_source: 'derived',
  },
  {
    spec_key: 'finish',
    label: 'Finish or colour',
    data_type: 'text',
    value: 'matt_black',
    unit: null,
    evidence: 'Matt Black finish',
    kind: 'conflict' as const,
    stored_value: 'chrome',
    stored_unit: null,
    stored_source: 'human',
  },
];

function makeClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function wrapper(client: QueryClient) {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('non-conflict seeding of the selection (AC-B.7)', () => {
  it('seeds selectedKeys with every proposal except conflicts', async () => {
    mockExtract.mockResolvedValue({
      product_code: 'SRT-WC-1001',
      engine: 'semantic',
      model: 'gpt-4o',
      proposals: PROPOSALS,
      unchanged: 0,
    });
    const client = makeClient();
    const { result } = renderHook(() => useSpecExtraction('p-1', 'SRT-WC-1001'), {
      wrapper: wrapper(client),
    });

    await act(async () => {
      await result.current.extract('Washdown with rimless, matt black finish');
    });

    await waitFor(() =>
      expect(result.current.selectedKeys.sort()).toEqual(['dim_height', 'seat_material']),
    );
    expect(result.current.selectedKeys).not.toContain('finish');
  });
});

describe('apply payload', () => {
  it('carries the evidence per selected entry, and only the selected entries', async () => {
    mockExtract.mockResolvedValue({
      product_code: 'SRT-WC-1001',
      engine: 'semantic',
      model: 'gpt-4o',
      proposals: PROPOSALS,
      unchanged: 0,
    });
    mockApply.mockResolvedValue({
      product_code: 'SRT-WC-1001',
      rows_written: 2,
      spec_keys: ['seat_material', 'dim_height'],
    });
    const client = makeClient();
    const { result } = renderHook(() => useSpecExtraction('p-1', 'SRT-WC-1001'), {
      wrapper: wrapper(client),
    });

    await act(async () => {
      await result.current.extract('Washdown with rimless, matt black finish');
    });
    await waitFor(() => expect(result.current.proposals).toHaveLength(3));

    await act(async () => {
      await result.current.apply();
    });

    expect(mockApply).toHaveBeenCalledWith('p-1', [
      { spec_key: 'seat_material', value: 'pp', unit: null, evidence: '*PP Seat Cover' },
      {
        spec_key: 'dim_height',
        value: 770,
        unit: 'mm',
        evidence: 'D: L680xW375xH770mm',
      },
    ]);
    // The unticked conflict never makes it into the batch.
    const sentKeys = mockApply.mock.calls[0][1].map((entry: { spec_key: string }) => entry.spec_key);
    expect(sentKeys).not.toContain('finish');
  });
});

describe('apply success toast reports the specification count, not the row fan-out', () => {
  it('says "2 specifications saved" when 2 keys fanned out to 4 written rows', async () => {
    mockExtract.mockResolvedValue({
      product_code: 'SRT-WC-1001',
      engine: 'semantic',
      model: 'gpt-4o',
      proposals: PROPOSALS,
      unchanged: 0,
    });
    // `rows_written` counts every COMPANY COPY of the code the write fanned out to
    // (2 keys x 2 copies = 4). The user ticked and applied 2 specifications; the
    // toast must count what they did, not the write's internal fan-out.
    mockApply.mockResolvedValue({
      product_code: 'SRT-WC-1001',
      rows_written: 4,
      spec_keys: ['seat_material', 'dim_height'],
    });
    const client = makeClient();
    const { result } = renderHook(() => useSpecExtraction('p-1', 'SRT-WC-1001'), {
      wrapper: wrapper(client),
    });

    await act(async () => {
      await result.current.extract('Washdown with rimless, matt black finish');
    });
    await waitFor(() => expect(result.current.proposals).toHaveLength(3));

    await act(async () => {
      await result.current.apply();
    });

    expect(toast.success).toHaveBeenCalledWith(
      '2 specifications saved',
      expect.objectContaining({ description: expect.any(String) }),
    );
  });
});

describe('query invalidation on apply', () => {
  it('invalidates both the detail key and the applicable-keys key', async () => {
    mockExtract.mockResolvedValue({
      product_code: 'SRT-WC-1001',
      engine: 'semantic',
      model: 'gpt-4o',
      proposals: PROPOSALS,
      unchanged: 0,
    });
    mockApply.mockResolvedValue({
      product_code: 'SRT-WC-1001',
      rows_written: 2,
      spec_keys: ['seat_material', 'dim_height'],
    });
    const client = makeClient();
    const invalidateSpy = vi.spyOn(client, 'invalidateQueries');
    const { result } = renderHook(() => useSpecExtraction('p-1', 'SRT-WC-1001'), {
      wrapper: wrapper(client),
    });

    await act(async () => {
      await result.current.extract('Washdown with rimless, matt black finish');
    });
    await act(async () => {
      await result.current.apply();
    });

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: DETAIL_KEY('p-1') });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: APPLICABLE_KEY('SRT-WC-1001') });
  });
});

describe('discard', () => {
  it('clears the result and the selection without writing anything', async () => {
    mockExtract.mockResolvedValue({
      product_code: 'SRT-WC-1001',
      engine: 'semantic',
      model: 'gpt-4o',
      proposals: PROPOSALS,
      unchanged: 0,
    });
    const client = makeClient();
    const { result } = renderHook(() => useSpecExtraction('p-1', 'SRT-WC-1001'), {
      wrapper: wrapper(client),
    });

    await act(async () => {
      await result.current.extract('Washdown with rimless, matt black finish');
    });
    await waitFor(() => expect(result.current.proposals).toHaveLength(3));

    act(() => {
      result.current.discard();
    });

    expect(result.current.result).toBeNull();
    expect(result.current.proposals).toEqual([]);
    expect(result.current.selectedKeys).toEqual([]);
    expect(mockApply).not.toHaveBeenCalled();
  });
});
