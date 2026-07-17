/**
 * SCM M4 Slice B — usePurchaseOrderActions hook (bulk-confirm + create-GR).
 * Both mutations must invalidate the PO-list cache (so the status chip +
 * on-order state refresh) and surface the extracted error on failure.
 *   AC-M4.6 (confirm drafts → active; create-GR from an active PO)
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));

import { usePurchaseOrderActions } from './usePurchaseOrderActions';

function ok(body: unknown) {
  return {
    ok: true,
    status: 200,
    headers: { get: () => 'application/json' },
    json: async () => body,
  } as unknown as Response;
}
function fail(detail: string) {
  return {
    ok: false,
    status: 400,
    headers: { get: () => 'application/json' },
    json: async () => ({ detail }),
    text: async () => JSON.stringify({ detail }),
  } as unknown as Response;
}

function makeWrapper() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const spy = vi.spyOn(client, 'invalidateQueries');
  const wrapper = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client }, children);
  return { spy, wrapper };
}

beforeEach(() => apiFetch.mockReset());

describe('usePurchaseOrderActions — confirm (AC-M4.6)', () => {
  it('confirm returns the count and invalidates the PO list', async () => {
    apiFetch.mockResolvedValue(ok({ confirmed_count: 3 }));
    const { spy, wrapper } = makeWrapper();
    const { result } = renderHook(() => usePurchaseOrderActions(), { wrapper });
    let res: { confirmed_count: number } | undefined;
    await act(async () => {
      res = await result.current.confirm.mutateAsync(['po-1', 'po-2', 'po-3']);
    });
    expect(res).toEqual({ confirmed_count: 3 });
    const keys = spy.mock.calls.map((c) => JSON.stringify((c[0] as { queryKey: unknown }).queryKey));
    expect(keys).toContain(JSON.stringify(['scm', 'purchase-orders']));
  });

  it('confirm surfaces the extracted error on failure', async () => {
    apiFetch.mockResolvedValue(fail('No drafts in selection'));
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => usePurchaseOrderActions(), { wrapper });
    await expect(
      act(async () => {
        await result.current.confirm.mutateAsync(['po-1']);
      }),
    ).rejects.toThrow('No drafts in selection');
  });
});

describe('usePurchaseOrderActions — create-GR (AC-M4.6)', () => {
  it('createGr returns the GR reference and invalidates the PO list', async () => {
    apiFetch.mockResolvedValue(ok({ gr_reference: 'GR-2026/07-0001' }));
    const { spy, wrapper } = makeWrapper();
    const { result } = renderHook(() => usePurchaseOrderActions(), { wrapper });
    let res: { gr_reference: string } | undefined;
    await act(async () => {
      res = await result.current.createGr.mutateAsync('po-9');
    });
    expect(res).toEqual({ gr_reference: 'GR-2026/07-0001' });
    const keys = spy.mock.calls.map((c) => JSON.stringify((c[0] as { queryKey: unknown }).queryKey));
    expect(keys).toContain(JSON.stringify(['scm', 'purchase-orders']));
  });

  it('createGr surfaces the extracted error on failure', async () => {
    apiFetch.mockResolvedValue(fail('PO is still a draft'));
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => usePurchaseOrderActions(), { wrapper });
    await expect(
      act(async () => {
        await result.current.createGr.mutateAsync('po-9');
      }),
    ).rejects.toThrow('PO is still a draft');
  });
});
