/**
 * SCM M4 Slice B - useDecisions hook (accept / adjust / reject / bulk mutations).
 * Each mutation must invalidate BOTH the decisions cache AND the PO-list cache
 * (so a freshly-drafted PO appears), and expose the extracted error on failure.
 *   AC-M4.5/M4.7/M4.8/M4.9 (decision mutations) · AC-M4.14 (decisions query → byId)
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));

import { useDecisionMutations, useRecommendationDecisions, decisionsKey } from './useDecisions';
import type { ReorderRecommendation } from '../types/reorder.types';

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

const rec = (over: Partial<ReorderRecommendation> = {}) =>
  ({ id: 'rec-1', sku: 'CW-BASIN-450', ...over }) as ReorderRecommendation;

function makeWrapper() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const spy = vi.spyOn(client, 'invalidateQueries');
  const wrapper = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client }, children);
  return { client, spy, wrapper };
}

beforeEach(() => apiFetch.mockReset());

describe('useRecommendationDecisions (AC-M4.14)', () => {
  it('indexes the fetched decisions by recommendation id', async () => {
    apiFetch.mockResolvedValue(
      ok({
        data: [
          { recommendation_id: 'rec-1', status: 'accepted', draft_po_number: 'PO-DRAFT-1', draft_po_id: 'po-1' },
          { recommendation_id: 'rec-2', status: 'dismissed' },
        ],
      }),
    );
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useRecommendationDecisions('run-1', true), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.byId['rec-1'].status).toBe('accepted');
    expect(result.current.byId['rec-2'].status).toBe('dismissed');
  });

  it('does not fetch when disabled', () => {
    const { wrapper } = makeWrapper();
    renderHook(() => useRecommendationDecisions('run-1', false), { wrapper });
    expect(apiFetch).not.toHaveBeenCalled();
  });
});

describe('useDecisionMutations - invalidation (AC-M4.5/M4.7/M4.8/M4.9)', () => {
  it('accept invalidates BOTH the decisions cache and the PO list', async () => {
    apiFetch.mockResolvedValue(ok({ draft_po_number: 'PO-DRAFT-1', draft_po_id: 'po-1', supplier_name: 'Acme' }));
    const { spy, wrapper } = makeWrapper();
    const { result } = renderHook(() => useDecisionMutations('run-1'), { wrapper });
    await act(async () => {
      await result.current.accept.mutateAsync(rec());
    });
    const keys = spy.mock.calls.map((c) => JSON.stringify((c[0] as { queryKey: unknown }).queryKey));
    expect(keys).toContain(JSON.stringify(decisionsKey('run-1')));
    expect(keys).toContain(JSON.stringify(['scm', 'purchase-orders']));
  });

  it('adjust invalidates both caches', async () => {
    apiFetch.mockResolvedValue(ok({ draft_po_number: 'PO-DRAFT-1', draft_po_id: 'po-1', supplier_name: 'Beta' }));
    const { spy, wrapper } = makeWrapper();
    const { result } = renderHook(() => useDecisionMutations('run-1'), { wrapper });
    await act(async () => {
      await result.current.adjust.mutateAsync({
        rec: rec(),
        payload: { override_qty: 10, override_supplier_code: null, reason_text: 'x' },
      });
    });
    const keys = spy.mock.calls.map((c) => JSON.stringify((c[0] as { queryKey: unknown }).queryKey));
    expect(keys).toContain(JSON.stringify(decisionsKey('run-1')));
    expect(keys).toContain(JSON.stringify(['scm', 'purchase-orders']));
  });

  it('reject invalidates both caches', async () => {
    apiFetch.mockResolvedValue(ok({}));
    const { spy, wrapper } = makeWrapper();
    const { result } = renderHook(() => useDecisionMutations('run-1'), { wrapper });
    await act(async () => {
      await result.current.reject.mutateAsync({ rec: rec(), payload: { reason_text: 'discontinued' } });
    });
    const keys = spy.mock.calls.map((c) => JSON.stringify((c[0] as { queryKey: unknown }).queryKey));
    expect(keys).toContain(JSON.stringify(decisionsKey('run-1')));
    expect(keys).toContain(JSON.stringify(['scm', 'purchase-orders']));
  });

  it('bulk-accept invalidates both caches', async () => {
    apiFetch.mockResolvedValue(ok({ accepted_count: 2, po_count: 1 }));
    const { spy, wrapper } = makeWrapper();
    const { result } = renderHook(() => useDecisionMutations('run-1'), { wrapper });
    await act(async () => {
      await result.current.bulkAccept.mutateAsync([rec({ id: 'a' }), rec({ id: 'b' })]);
    });
    const keys = spy.mock.calls.map((c) => JSON.stringify((c[0] as { queryKey: unknown }).queryKey));
    expect(keys).toContain(JSON.stringify(['scm', 'purchase-orders']));
  });
});

describe('useDecisionMutations - error propagation', () => {
  it('rejects with the extracted backend message so the caller can toast it', async () => {
    apiFetch.mockResolvedValue(fail('Recommendation already decided'));
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useDecisionMutations('run-1'), { wrapper });
    await expect(
      act(async () => {
        await result.current.accept.mutateAsync(rec());
      }),
    ).rejects.toThrow('Recommendation already decided');
  });
});
