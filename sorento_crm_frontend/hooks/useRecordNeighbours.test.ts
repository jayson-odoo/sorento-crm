/**
 * Tests for the generic useRecordNeighbours hook.
 *
 * Verifies the hook contract from
 * docs/plans/PLAN-record-navigation-standardization.md §7:
 * - builds the query string from listParams (object OR URLSearchParams)
 * - strips `id` from listParams (current id set explicitly)
 * - disabled when no currentId (no fetch)
 * - maps the snake_case backend response to camelCase result fields
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { useRecordNeighbours } from './useRecordNeighbours';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({
  apiFetch: (...args: unknown[]) => apiFetch(...args),
}));
vi.mock('@/lib/api-client', () => ({
  extractApiError: async () => 'error',
}));

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return React.createElement(QueryClientProvider, { client }, children);
}

function okResponse(body: unknown) {
  return { ok: true, json: async () => body } as unknown as Response;
}

const PATH = '/api/v1/complaints-management/complaints/neighbours';

beforeEach(() => {
  apiFetch.mockReset();
});

describe('useRecordNeighbours', () => {
  it('does not fetch when currentId is null (disabled)', () => {
    apiFetch.mockResolvedValue(
      okResponse({ total: 0, index: null, prev_id: null, next_id: null }),
    );
    renderHook(() => useRecordNeighbours(PATH, null), { wrapper });
    expect(apiFetch).not.toHaveBeenCalled();
  });

  it('maps snake_case response to camelCase result', async () => {
    apiFetch.mockResolvedValue(
      okResponse({ total: 23, index: 6, prev_id: 'pPrev', next_id: 'nNext' }),
    );
    const { result } = renderHook(
      () => useRecordNeighbours(PATH, 'cur-1'),
      { wrapper },
    );
    await waitFor(() => expect(result.current.total).toBe(23));
    expect(result.current.prevId).toBe('pPrev');
    expect(result.current.nextId).toBe('nNext');
    expect(result.current.index).toBe(6);
  });

  it('builds the query string from an object listParams and sets id explicitly', async () => {
    apiFetch.mockResolvedValue(
      okResponse({ total: 1, index: 1, prev_id: null, next_id: null }),
    );
    renderHook(
      () =>
        useRecordNeighbours(PATH, 'cur-1', {
          query: '04',
          sort: 'customer_name',
          dir: 'desc',
          status: 'new',
        }),
      { wrapper },
    );
    await waitFor(() => expect(apiFetch).toHaveBeenCalled());
    const url = apiFetch.mock.calls[0][0] as string;
    expect(url.startsWith(`${PATH}?`)).toBe(true);
    const sp = new URLSearchParams(url.split('?')[1]);
    expect(sp.get('id')).toBe('cur-1');
    expect(sp.get('query')).toBe('04');
    expect(sp.get('sort')).toBe('customer_name');
    expect(sp.get('dir')).toBe('desc');
    expect(sp.get('status')).toBe('new');
  });

  it('accepts URLSearchParams as listParams', async () => {
    apiFetch.mockResolvedValue(
      okResponse({ total: 1, index: 1, prev_id: null, next_id: null }),
    );
    const lp = new URLSearchParams({ query: 'abc', dir: 'asc' });
    renderHook(() => useRecordNeighbours(PATH, 'cur-2', lp), { wrapper });
    await waitFor(() => expect(apiFetch).toHaveBeenCalled());
    const url = apiFetch.mock.calls[0][0] as string;
    const sp = new URLSearchParams(url.split('?')[1]);
    expect(sp.get('id')).toBe('cur-2');
    expect(sp.get('query')).toBe('abc');
  });

  it('strips a stray `id` from listParams (explicit currentId wins)', async () => {
    apiFetch.mockResolvedValue(
      okResponse({ total: 1, index: 1, prev_id: null, next_id: null }),
    );
    renderHook(
      () =>
        useRecordNeighbours(PATH, 'real-id', {
          id: 'should-be-ignored',
          query: 'x',
        }),
      { wrapper },
    );
    await waitFor(() => expect(apiFetch).toHaveBeenCalled());
    const url = apiFetch.mock.calls[0][0] as string;
    const sp = new URLSearchParams(url.split('?')[1]);
    expect(sp.get('id')).toBe('real-id');
  });

  it('omits empty/undefined listParam values from the query string', async () => {
    apiFetch.mockResolvedValue(
      okResponse({ total: 1, index: 1, prev_id: null, next_id: null }),
    );
    renderHook(
      () =>
        useRecordNeighbours(PATH, 'cur-3', {
          query: '',
          status: undefined,
          sort: 'created_at',
        }),
      { wrapper },
    );
    await waitFor(() => expect(apiFetch).toHaveBeenCalled());
    const url = apiFetch.mock.calls[0][0] as string;
    const sp = new URLSearchParams(url.split('?')[1]);
    expect(sp.has('query')).toBe(false);
    expect(sp.has('status')).toBe(false);
    expect(sp.get('sort')).toBe('created_at');
  });
});
