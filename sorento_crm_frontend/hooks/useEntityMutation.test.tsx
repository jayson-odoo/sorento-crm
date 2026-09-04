/**
 * S7-01 - the shared optimistic-mutation factory.
 *
 * useEntityMutation's whole reason to exist is that a switch flips the instant
 * it is pressed, not after the round trip lands, and that a failed write puts
 * the row back the way it was. These tests pin down both halves, on the two
 * cache shapes the factory actually knows: a bare `Row[]` and a `{ data: Row[] }`
 * envelope.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { useEntityMutation } from './useEntityMutation';

vi.mock('@/lib/toast', () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

import { toast } from '@/lib/toast';

type Row = { id: string; active: boolean };

function makeWrapper(queryClient: QueryClient) {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe('useEntityMutation (S7-01)', () => {
  beforeEach(() => {
    vi.mocked(toast.error).mockClear();
    vi.mocked(toast.success).mockClear();
  });

  it('patches a bare Row[] cache before the mutation resolves', async () => {
    const queryClient = new QueryClient();
    queryClient.setQueryData<Row[]>(['rows'], [
      { id: '1', active: false },
      { id: '2', active: false },
    ]);

    const gate = deferred<{ id: string }>();

    const { result } = renderHook(
      () =>
        useEntityMutation<{ id: string }, { id: string }>({
          mutationFn: async (vars) => gate.promise.then(() => vars),
          keys: [['rows']],
          matchRow: (row, vars) => row.id === vars.id,
          patchRow: () => ({ active: true }),
        }),
      { wrapper: makeWrapper(queryClient) },
    );

    act(() => {
      result.current.mutate({ id: '1' });
    });

    // Applied before the mutationFn's own promise has resolved - the request
    // is still pending on `gate`.
    await waitFor(() => {
      const rows = queryClient.getQueryData<Row[]>(['rows'])!;
      expect(rows.find((r) => r.id === '1')?.active).toBe(true);
    });
    const midFlightRows = queryClient.getQueryData<Row[]>(['rows'])!;
    expect(midFlightRows.find((r) => r.id === '2')?.active).toBe(false);
    expect(result.current.isSuccess).toBe(false);

    gate.resolve({ id: '1' });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
  });

  it('patches the { data: Row[] } envelope shape the same way', async () => {
    const queryClient = new QueryClient();
    queryClient.setQueryData(['rows-env'], {
      data: [
        { id: '1', active: false },
        { id: '2', active: false },
      ],
    });

    const gate = deferred<{ id: string }>();

    const { result } = renderHook(
      () =>
        useEntityMutation<{ id: string }, { id: string }>({
          mutationFn: async (vars) => gate.promise.then(() => vars),
          keys: [['rows-env']],
          matchRow: (row, vars) => row.id === vars.id,
          patchRow: () => ({ active: true }),
        }),
      { wrapper: makeWrapper(queryClient) },
    );

    act(() => {
      result.current.mutate({ id: '1' });
    });

    await waitFor(() => {
      const cached = queryClient.getQueryData<{ data: Row[] }>(['rows-env'])!;
      expect(cached.data.find((r) => r.id === '1')?.active).toBe(true);
    });
    const cached = queryClient.getQueryData<{ data: Row[] }>(['rows-env'])!;
    expect(cached.data.find((r) => r.id === '2')?.active).toBe(false);

    gate.resolve({ id: '1' });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
  });

  it('rolls back the optimistic patch when the write fails', async () => {
    const queryClient = new QueryClient();
    queryClient.setQueryData<Row[]>(['rows'], [{ id: '1', active: false }]);

    const gate = deferred<{ id: string }>();

    const { result } = renderHook(
      () =>
        useEntityMutation<{ id: string }, { id: string }>({
          mutationFn: async (vars) => gate.promise.then(() => vars),
          keys: [['rows']],
          matchRow: (row, vars) => row.id === vars.id,
          patchRow: () => ({ active: true }),
          errorMessage: 'Could not update the row',
        }),
      { wrapper: makeWrapper(queryClient) },
    );

    act(() => {
      result.current.mutate({ id: '1' });
    });

    await waitFor(() => {
      const rows = queryClient.getQueryData<Row[]>(['rows'])!;
      expect(rows.find((r) => r.id === '1')?.active).toBe(true);
    });

    gate.reject(new Error('server rejected it'));
    await waitFor(() => expect(result.current.isError).toBe(true));

    const rowsAfterError = queryClient.getQueryData<Row[]>(['rows'])!;
    expect(rowsAfterError.find((r) => r.id === '1')?.active).toBe(false);
    expect(toast.error).toHaveBeenCalledWith('Could not update the row: server rejected it');
  });

  it('rolls back the { data: Row[] } envelope shape on failure too', async () => {
    const queryClient = new QueryClient();
    queryClient.setQueryData(['rows-env'], { data: [{ id: '1', active: false }] });

    const gate = deferred<{ id: string }>();

    const { result } = renderHook(
      () =>
        useEntityMutation<{ id: string }, { id: string }>({
          mutationFn: async (vars) => gate.promise.then(() => vars),
          keys: [['rows-env']],
          matchRow: (row, vars) => row.id === vars.id,
          patchRow: () => ({ active: true }),
        }),
      { wrapper: makeWrapper(queryClient) },
    );

    act(() => {
      result.current.mutate({ id: '1' });
    });

    await waitFor(() => {
      const cached = queryClient.getQueryData<{ data: Row[] }>(['rows-env'])!;
      expect(cached.data[0].active).toBe(true);
    });

    gate.reject(new Error('nope'));
    await waitFor(() => expect(result.current.isError).toBe(true));

    const cached = queryClient.getQueryData<{ data: Row[] }>(['rows-env'])!;
    expect(cached.data[0].active).toBe(false);
  });
});
