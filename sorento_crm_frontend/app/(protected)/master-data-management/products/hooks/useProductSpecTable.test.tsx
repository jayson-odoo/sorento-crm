/**
 * Tests for useProductSpecTable — the tab's error state.
 *
 * A failed applicable-keys fetch must surface as the tab's error, not silently render
 * every stored row as "Not in the registry": with an empty registry the table reads
 * as data corruption when the truth is a transient network failure.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
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
} from '../../product-specifications/services/productSpecService';
import { useProductSpecTable } from './useProductSpecTable';

const mockDetail = getProductSpecDetail as unknown as ReturnType<typeof vi.fn>;
const mockKeys = getApplicableSpecKeys as unknown as ReturnType<typeof vi.fn>;
const mockAddValue = addValueToSpecKey as unknown as ReturnType<typeof vi.fn>;

const DETAIL = {
  product_id: 'p-1',
  product_code: 'WC100',
  spec: { values: {}, provenance: {}, rendered_text: null, status: 'ok', derived_at: null },
  exceptions: [],
};

function wrapper() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
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
