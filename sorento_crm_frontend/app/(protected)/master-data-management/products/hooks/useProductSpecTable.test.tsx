/**
 * Tests for useProductSpecTable - the tab's error state.
 *
 * A failed applicable-keys fetch must surface as the tab's error, not silently render
 * every stored row as "Not in the registry": with an empty registry the table reads
 * as data corruption when the truth is a transient network failure.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));
vi.mock('../../spec-verification/services/specVerificationService', () => ({
  SpecVerifyConflictError: class extends Error {},
  verifySpec: vi.fn(),
  unverifySpec: vi.fn(),
}));
vi.mock('../../product-specifications/services/productSpecService', () => ({
  addValueToSpecKey: vi.fn(),
  clearSpecValueByHand: vi.fn(),
  createSpecKey: vi.fn(),
  getApplicableSpecKeys: vi.fn(),
  getProductSpecDetail: vi.fn(),
  getSimilarSpecKey: vi.fn(),
  setSpecValueByHand: vi.fn(),
}));

import {
  addValueToSpecKey,
  getApplicableSpecKeys,
  getProductSpecDetail,
  setSpecValueByHand,
} from '../../product-specifications/services/productSpecService';
import { WORKLIST_KEY } from '../../spec-verification/hooks/useSpecVerification';
import { verifySpec } from '../../spec-verification/services/specVerificationService';
import type { SpecVerificationWorklistResponse } from '../../spec-verification/types/specVerification.types';
import { useProductSpecTable } from './useProductSpecTable';

const mockDetail = getProductSpecDetail as unknown as ReturnType<typeof vi.fn>;
const mockKeys = getApplicableSpecKeys as unknown as ReturnType<typeof vi.fn>;
const mockAddValue = addValueToSpecKey as unknown as ReturnType<typeof vi.fn>;
const mockSetValue = setSpecValueByHand as unknown as ReturnType<typeof vi.fn>;
const mockVerify = verifySpec as unknown as ReturnType<typeof vi.fn>;

const DETAIL = {
  product_id: 'p-1',
  product_code: 'WC100',
  spec: { values: {}, provenance: {}, rendered_text: null, status: 'ok', derived_at: null },
  exceptions: [],
};

function wrapper(client = new QueryClient({ defaultOptions: { queries: { retry: false } } })) {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

describe('useProductSpecTable error state', () => {
  beforeEach(() => vi.clearAllMocks());

  it('surfaces a failed applicable-keys fetch instead of an empty registry', async () => {
    mockDetail.mockResolvedValue(DETAIL);
    mockKeys.mockRejectedValue(new Error('registry down'));

    const { result } = renderHook(() => useProductSpecTable('p-1'), { wrapper: wrapper() });

    await waitFor(() => expect(result.current.error).toBe('registry down'));
  });

  it('reports no error when both fetches answer', async () => {
    mockDetail.mockResolvedValue(DETAIL);
    mockKeys.mockResolvedValue({ keys: [] });

    const { result } = renderHook(() => useProductSpecTable('p-1'), { wrapper: wrapper() });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.error).toBeNull();
  });
});

describe('useProductSpecTable addValue', () => {
  beforeEach(() => vi.clearAllMocks());

  it('sends the new word alone, not the vocabulary its own snapshot knows', async () => {
    mockDetail.mockResolvedValue(DETAIL);
    mockKeys.mockResolvedValue({
      keys: [
        {
          spec_key: 'finish',
          label: 'Finish',
          data_type: 'enum',
          unit: null,
          // The snapshot this page loaded with. Rebuilding the payload from it is
          // what deleted a word somebody else added in the meantime.
          allowed_values: ['chrome'],
          synonyms: {},
          applicable: true,
          held: false,
        },
      ],
    });
    mockAddValue.mockResolvedValue({ spec_key: 'finish' });

    const { result } = renderHook(() => useProductSpecTable('p-1'), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await result.current.addValue('finish', 'brushed brass');

    expect(mockAddValue).toHaveBeenCalledWith('finish', 'brushed brass');
  });
});

describe('useProductSpecTable value writes and the verification worklist', () => {
  beforeEach(() => vi.clearAllMocks());

  it('invalidates the worklist, because a value write withdraws the code\'s stamp', async () => {
    // The worklist shows this code's hash and its verification pill. A write moves
    // both, so leaving that cache alone is how the list and the record end up
    // disagreeing about a code somebody just edited.
    mockDetail.mockResolvedValue(DETAIL);
    mockKeys.mockResolvedValue({ keys: [] });
    mockSetValue.mockResolvedValue({ product_code: 'WC100' });

    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidate = vi.spyOn(client, 'invalidateQueries');
    const { result } = renderHook(() => useProductSpecTable('p-1'), {
      wrapper: wrapper(client),
    });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    invalidate.mockClear();

    await result.current.setValue('material', 'ceramic');

    expect(invalidate).toHaveBeenCalledWith({ queryKey: [WORKLIST_KEY] });
  });
});

describe('useProductSpecTable verify and the verification worklist', () => {
  beforeEach(() => vi.clearAllMocks());

  const VERIFIED_BLOCK = {
    state: 'verified' as const,
    verified_by_name: 'Jay Odoo',
    verified_at: '2026-08-17T09:00:00',
    invalidated_at: null,
    invalidated_reason: null,
    invalidated_by_name: null,
    invalidated_diff: null,
  };

  function worklistRow(code: string): SpecVerificationWorklistResponse {
    return {
      data: [
        {
          product_id: 'p-1',
          product_code: code,
          product_name: code,
          class_label: 'Kitchen Sink',
          brand_name: null,
          is_discontinued: false,
          coverage: { have: 1, applicable: 2, items: [] },
          open_exceptions: 0,
          values_hash: 'hash-1',
          verification: {
            state: 'unverified',
            verified_by_name: null,
            verified_at: null,
            invalidated_at: null,
            invalidated_reason: null,
            invalidated_by_name: null,
            invalidated_diff: null,
          },
        },
      ],
      pagination: { total: 1, page: 1, limit: 25 },
      summary: { total: 1, verified: 0, needs_reverify: 0, unverified: 1 },
      classes: ['Kitchen Sink'],
    };
  }

  it("patches the worklist's row in place, so the list already reads Verified on return", async () => {
    // The reviewer came FROM that list and goes straight back to it. Invalidating alone
    // leaves the row on its old state until the refetch answers - which is the exact
    // moment they are looking at it (captain ruling 2026-08-17).
    mockDetail.mockResolvedValue({ ...DETAIL, values_hash: 'hash-1' });
    mockKeys.mockResolvedValue({ keys: [] });
    mockVerify.mockResolvedValue({
      product_code: 'WC100',
      outcome: 'verified',
      values_hash: 'hash-2',
      verification: VERIFIED_BLOCK,
    });

    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const key = [WORKLIST_KEY, 0, 25, [], '', '', '', false];
    client.setQueryData(key, worklistRow('WC100'));

    const { result } = renderHook(() => useProductSpecTable('p-1'), {
      wrapper: wrapper(client),
    });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    result.current.verify();

    await waitFor(() => {
      const cached = client.getQueryData<SpecVerificationWorklistResponse>(key);
      expect(cached?.data[0].verification.state).toBe('verified');
      expect(cached?.data[0].values_hash).toBe('hash-2');
      expect(cached?.summary.verified).toBe(1);
    });
    expect(mockVerify).toHaveBeenCalledWith({
      product_code: 'WC100',
      values_hash: 'hash-1',
    });
  });
});
