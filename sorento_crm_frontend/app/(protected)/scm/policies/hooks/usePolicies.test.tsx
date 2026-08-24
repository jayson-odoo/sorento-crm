/**
 * usePolicies - query + mutation hook tests (AC-EDIT-5, AC-STD-2).
 *
 * Mocks the feature service so the hooks are exercised in isolation:
 * - query hooks return the resolved data
 * - create/update/delete mutations invalidate the reorder list key + toast on
 *     success, and toast the extracted message on error
 * - classification / supplier-scoring save mutations behave the same
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const svc = vi.hoisted(() => ({
  listReorderPolicies: vi.fn(),
  createReorderPolicy: vi.fn(),
  updateReorderPolicy: vi.fn(),
  deleteReorderPolicy: vi.fn(),
  getClassification: vi.fn(),
  saveClassification: vi.fn(),
  getSupplierScoring: vi.fn(),
  saveSupplierScoring: vi.fn(),
  resolvePolicy: vi.fn(),
  getProductScopeOptions: vi.fn(),
  getClassScopeOptions: vi.fn(),
  getWarehouseScopeOptions: vi.fn(),
}));
vi.mock('../services/scmPolicyService', () => svc);

const toastSuccess = vi.fn();
const toastError = vi.fn();
vi.mock('sonner', () => ({
  toast: { success: (...a: unknown[]) => toastSuccess(...a), error: (...a: unknown[]) => toastError(...a) },
}));

import {
  useReorderPolicies,
  useCreatePolicy,
  useUpdatePolicy,
  useDeletePolicy,
  useClassification,
  useSaveClassification,
  useSupplierScoring,
  useSaveSupplierScoring,
  useResolvePolicy,
} from './usePolicies';

let client: QueryClient;
function wrapper({ children }: { children: React.ReactNode }) {
  return React.createElement(QueryClientProvider, { client }, children);
}

beforeEach(() => {
  Object.values(svc).forEach((f) => f.mockReset());
  toastSuccess.mockReset();
  toastError.mockReset();
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
});

describe('query hooks return data', () => {
  it('useReorderPolicies resolves the list page', async () => {
    svc.listReorderPolicies.mockResolvedValue({ data: [{ id: 'pol-1' }], total: 1 });
    const { result } = renderHook(() => useReorderPolicies({ pageIndex: 0, pageSize: 50 }), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.total).toBe(1);
    expect(svc.listReorderPolicies).toHaveBeenCalledWith({ pageIndex: 0, pageSize: 50 });
  });

  it('useClassification resolves the single row', async () => {
    svc.getClassification.mockResolvedValue({ abc_a_pct: 0.8, exists: true });
    const { result } = renderHook(() => useClassification(), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.exists).toBe(true);
  });

  it('useSupplierScoring resolves the single row', async () => {
    svc.getSupplierScoring.mockResolvedValue({ delivery_weight: 0.6, exists: true });
    const { result } = renderHook(() => useSupplierScoring(), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.delivery_weight).toBe(0.6);
  });
});

describe('create/update/delete mutations invalidate + toast (AC-EDIT-5)', () => {
  it('create: success invalidates the reorder key + success toast', async () => {
    svc.createReorderPolicy.mockResolvedValue({ id: 'pol-new' });
    const spy = vi.spyOn(client, 'invalidateQueries');
    const { result } = renderHook(() => useCreatePolicy(), { wrapper });
    await act(async () => {
      await result.current.mutateAsync({ scope_type: 'product_class' } as never);
    });
    expect(spy).toHaveBeenCalledWith({ queryKey: ['scm', 'policies', 'reorder'] });
    expect(toastSuccess).toHaveBeenCalledWith('Policy created');
  });

  it('create: error toasts the extracted message', async () => {
    svc.createReorderPolicy.mockRejectedValue(new Error('A policy already exists for this scope'));
    const { result } = renderHook(() => useCreatePolicy(), { wrapper });
    await act(async () => {
      await result.current.mutateAsync({} as never).catch(() => {});
    });
    await waitFor(() =>
      expect(toastError).toHaveBeenCalledWith('A policy already exists for this scope'),
    );
    expect(toastSuccess).not.toHaveBeenCalled();
  });

  it('update: success invalidates + success toast', async () => {
    svc.updateReorderPolicy.mockResolvedValue({ id: 'pol-1' });
    const spy = vi.spyOn(client, 'invalidateQueries');
    const { result } = renderHook(() => useUpdatePolicy(), { wrapper });
    await act(async () => {
      await result.current.mutateAsync({ id: 'pol-1', body: {} as never });
    });
    expect(spy).toHaveBeenCalledWith({ queryKey: ['scm', 'policies', 'reorder'] });
    expect(toastSuccess).toHaveBeenCalledWith('Policy updated');
  });

  it('update: error toasts the extracted message', async () => {
    svc.updateReorderPolicy.mockRejectedValue(new Error('bad'));
    const { result } = renderHook(() => useUpdatePolicy(), { wrapper });
    await act(async () => {
      await result.current.mutateAsync({ id: 'pol-1', body: {} as never }).catch(() => {});
    });
    await waitFor(() => expect(toastError).toHaveBeenCalledWith('bad'));
  });

  it('delete: success invalidates the reorder key', async () => {
    svc.deleteReorderPolicy.mockResolvedValue(undefined);
    const spy = vi.spyOn(client, 'invalidateQueries');
    const { result } = renderHook(() => useDeletePolicy(), { wrapper });
    await act(async () => {
      await result.current.mutateAsync('pol-1');
    });
    expect(spy).toHaveBeenCalledWith({ queryKey: ['scm', 'policies', 'reorder'] });
  });

  it('delete: error toasts the extracted message (global not deletable)', async () => {
    svc.deleteReorderPolicy.mockRejectedValue(new Error('The global default policy cannot be deleted'));
    const { result } = renderHook(() => useDeletePolicy(), { wrapper });
    await act(async () => {
      await result.current.mutateAsync('pol-global').catch(() => {});
    });
    await waitFor(() =>
      expect(toastError).toHaveBeenCalledWith('The global default policy cannot be deleted'),
    );
  });
});

describe('global-form save mutations invalidate + toast (AC-CFG-2 / AC-SUP-2)', () => {
  it('saveClassification: success invalidates classification key + toast', async () => {
    svc.saveClassification.mockResolvedValue({ exists: true });
    const spy = vi.spyOn(client, 'invalidateQueries');
    const { result } = renderHook(() => useSaveClassification(), { wrapper });
    await act(async () => {
      await result.current.mutateAsync({ abc_a_pct: 0.8, abc_b_pct: 0.15, xyz_x_max: 0.5, xyz_y_max: 1 });
    });
    expect(spy).toHaveBeenCalledWith({ queryKey: ['scm', 'policies', 'classification'] });
    expect(toastSuccess).toHaveBeenCalledWith('Classification thresholds saved');
  });

  it('saveSupplierScoring: error toasts the extracted message', async () => {
    svc.saveSupplierScoring.mockRejectedValue(new Error('weights must add up to 1.0'));
    const { result } = renderHook(() => useSaveSupplierScoring(), { wrapper });
    await act(async () => {
      await result.current
        .mutateAsync({ delivery_weight: 0.6, quality_weight: 0.6, grace_days: 0, min_sample_size: 1 })
        .catch(() => {});
    });
    await waitFor(() => expect(toastError).toHaveBeenCalledWith('weights must add up to 1.0'));
  });
});

describe('useResolvePolicy (AC-PREV-1)', () => {
  it('resolves the preview result via the service', async () => {
    svc.resolvePolicy.mockResolvedValue({ winner: { scope_type: 'global' }, chain: [] });
    const { result } = renderHook(() => useResolvePolicy(), { wrapper });
    await act(async () => {
      await result.current.mutateAsync({ productId: 'prd-1', warehouseCode: null });
    });
    expect(svc.resolvePolicy).toHaveBeenCalledWith('prd-1', null);
    await waitFor(() => expect(result.current.data?.winner?.scope_type).toBe('global'));
  });

  it('error toasts the extracted message', async () => {
    svc.resolvePolicy.mockRejectedValue(new Error('Product not found'));
    const { result } = renderHook(() => useResolvePolicy(), { wrapper });
    await act(async () => {
      await result.current.mutateAsync({ productId: 'nope', warehouseCode: null }).catch(() => {});
    });
    await waitFor(() => expect(toastError).toHaveBeenCalledWith('Product not found'));
  });
});
