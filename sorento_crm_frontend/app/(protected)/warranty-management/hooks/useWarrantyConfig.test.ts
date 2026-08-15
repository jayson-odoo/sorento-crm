/**
 * `useWarrantyConfig` - S7b Phase 2c gate, Group 2 item 8.
 *
 * Pins `sorting` as part of `usePolicies`'s react-query `queryKey`. Leave it
 * out and a grid column-header click changes `sorting` while the key stays
 * identical, so react-query serves the cached page and never refetches: every
 * column header on the Policies grid goes dead, silently, with no error to
 * point at. The sort is server-side (`manualSorting`), which is exactly why
 * the key has to carry it.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { SortingState } from '@tanstack/react-table';

vi.mock('../services/warrantyConfigService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../services/warrantyConfigService')>();
  return { ...actual, listPolicies: vi.fn() };
});

import { listPolicies, type PolicyListQuery } from '../services/warrantyConfigService';
import { usePolicies } from './useWarrantyConfig';

const mockedListPolicies = vi.mocked(listPolicies);

const PAGE = { data: [], pagination: { total: 0, page: 1, limit: 10 }, empty: true };

beforeEach(() => {
  mockedListPolicies.mockReset();
  mockedListPolicies.mockResolvedValue(PAGE);
});

describe('usePolicies - refetches when sorting changes (dead column-header click bug)', () => {
  it('calls listPolicies a second time when `sorting` changes with page/size/search held fixed', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const wrapper = ({ children }: { children: React.ReactNode }) =>
      React.createElement(QueryClientProvider, { client: qc }, children);

    const { result, rerender } = renderHook(
      (params: PolicyListQuery) => usePolicies(params),
      {
        wrapper,
        initialProps: { pageIndex: 0, pageSize: 10, searchQuery: '', sorting: [] as SortingState },
      },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockedListPolicies).toHaveBeenCalledTimes(1);

    // Same page/size/search: only sorting changes, as a column-header click does.
    rerender({
      pageIndex: 0,
      pageSize: 10,
      searchQuery: '',
      sorting: [{ id: 'version', desc: true }] as SortingState,
    });

    await waitFor(() => expect(mockedListPolicies).toHaveBeenCalledTimes(2));
    expect(mockedListPolicies).toHaveBeenLastCalledWith(
      expect.objectContaining({ sorting: [{ id: 'version', desc: true }] }),
    );
  });

  it('calling toggleSorting to desc after asc refetches a third time (both directions are live)', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const wrapper = ({ children }: { children: React.ReactNode }) =>
      React.createElement(QueryClientProvider, { client: qc }, children);

    const { result, rerender } = renderHook(
      (params: PolicyListQuery) => usePolicies(params),
      {
        wrapper,
        initialProps: { pageIndex: 0, pageSize: 10, searchQuery: '', sorting: [] as SortingState },
      },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    rerender({
      pageIndex: 0,
      pageSize: 10,
      searchQuery: '',
      sorting: [{ id: 'effective_from', desc: false }] as SortingState,
    });
    await waitFor(() => expect(mockedListPolicies).toHaveBeenCalledTimes(2));

    rerender({
      pageIndex: 0,
      pageSize: 10,
      searchQuery: '',
      sorting: [{ id: 'effective_from', desc: true }] as SortingState,
    });
    await waitFor(() => expect(mockedListPolicies).toHaveBeenCalledTimes(3));
  });
});
