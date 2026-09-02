/**
 * item 11 - the save mutation follows the invalidate + toast convention: it must
 * toast on success as every other mutation hook does, not just invalidate quietly.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const updateSearchPolicy = vi.fn();
vi.mock(
  '@/app/(protected)/master-data-management/product-specifications/services/productSpecService',
  () => ({
    updateSearchPolicy: (...a: unknown[]) => updateSearchPolicy(...a),
  }),
);

const toastSuccess = vi.fn();
const toastError = vi.fn();
vi.mock('@/lib/toast', () => ({
  toast: { success: (...a: unknown[]) => toastSuccess(...a), error: (...a: unknown[]) => toastError(...a) },
}));

import { useSearchPolicyMutations } from './useSearchPolicyMutations';

let client: QueryClient;
function wrapper({ children }: { children: React.ReactNode }) {
  return React.createElement(QueryClientProvider, { client }, children);
}

beforeEach(() => {
  updateSearchPolicy.mockReset();
  toastSuccess.mockReset();
  toastError.mockReset();
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
});

describe('useSearchPolicyMutations', () => {
  it('toasts "Search ranking saved" on success', async () => {
    updateSearchPolicy.mockResolvedValue({ policy_key: 'class_boost', value: 7 });
    const { result } = renderHook(() => useSearchPolicyMutations(), { wrapper });

    act(() => {
      result.current.save.mutate({ policyKey: 'class_boost', value: 7 });
    });

    await waitFor(() => expect(toastSuccess).toHaveBeenCalledWith('Search ranking saved'));
  });

  it('toasts the error message on failure, not a success toast', async () => {
    updateSearchPolicy.mockRejectedValue(new Error('Failed to save the search setting'));
    const { result } = renderHook(() => useSearchPolicyMutations(), { wrapper });

    act(() => {
      result.current.save.mutate({ policyKey: 'class_boost', value: 7 });
    });

    await waitFor(() =>
      expect(toastError).toHaveBeenCalledWith('Failed to save the search setting'),
    );
    expect(toastSuccess).not.toHaveBeenCalled();
  });
});
