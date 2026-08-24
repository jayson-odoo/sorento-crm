/**
 * Tests for useCompilePromotionsPdf - the Compile-PDF bulk-action mutation.
 *
 * Verifies it POSTs the selected ids (order preserved), invalidates the
 * ['my-downloads'] cache + toasts on success, and toasts on error.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));
vi.mock('../services/promotionService', () => ({
  compilePromotionsPdf: vi.fn(),
}));

import { toast } from 'sonner';
import { compilePromotionsPdf } from '../services/promotionService';
import { useCompilePromotionsPdf } from './usePromotions';

const mockCompile = compilePromotionsPdf as unknown as ReturnType<typeof vi.fn>;

function wrapper(client: QueryClient) {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

describe('useCompilePromotionsPdf', () => {
  beforeEach(() => vi.clearAllMocks());

  it('POSTs the ids in order, invalidates my-downloads, toasts success', async () => {
    mockCompile.mockResolvedValue({ download_id: 'dl-1' });
    const client = new QueryClient();
    const invalidateSpy = vi.spyOn(client, 'invalidateQueries');

    const { result } = renderHook(() => useCompilePromotionsPdf(), {
      wrapper: wrapper(client),
    });

    result.current.mutate(['p-a', 'p-b', 'p-c']);

    await waitFor(() => expect(mockCompile).toHaveBeenCalledTimes(1));
    // Ids passed through unchanged (grid display order).
    expect(mockCompile).toHaveBeenCalledWith(['p-a', 'p-b', 'p-c']);

    await waitFor(() =>
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['my-downloads'] }),
    );
    await waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith(
        'Preparing PDF… it will appear in My Downloads.',
      ),
    );
  });

  it('toasts the error message on failure', async () => {
    mockCompile.mockRejectedValue(new Error('Redis down'));
    const client = new QueryClient();

    const { result } = renderHook(() => useCompilePromotionsPdf(), {
      wrapper: wrapper(client),
    });

    result.current.mutate(['p-a']);

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Redis down'));
  });
});
